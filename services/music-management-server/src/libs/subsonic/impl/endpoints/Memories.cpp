/*
 * copyright (c) 2026 emeric poupon
 *
 * This file is part of LMS.
 *
 * LMS is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * LMS is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with LMS.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "Memories.hpp"

#include "../ParameterParsing.hpp"
#include "core/PartialDateTime.hpp"
#include "core/Service.hpp"
#include "database/Session.hpp"
#include "database/objects/User.hpp"
#include "responses/Song.hpp"
#include "services/feedback/IFeedbackService.hpp"
#include "services/scrobbling/IScrobblingService.hpp"

#include <algorithm>
#include <functional>
#include <map>
#include <string>
#include <unordered_map>

namespace lms::api::subsonic
{
    namespace memories
    {
        std::vector<Group> groupByYear(const std::vector<DatedTrack>& tracks, std::size_t maxPerYear)
        {
            // Sorted on a descending key, so the newest year falls out first without a second pass.
            std::map<int, std::vector<DatedTrack>, std::greater<int>> byYear;
            for (const DatedTrack& track : tracks)
                byYear[track.year].push_back(track);

            std::vector<Group> groups;
            groups.reserve(byYear.size());

            for (auto& [year, yearTracks] : byYear)
            {
                // Most loved first, so truncation keeps the best of the year rather than the head of
                // the query. The date only separates tracks the listener treats identically, which
                // preserves the older rule that an exact anniversary survives a near miss.
                std::sort(yearTracks.begin(), yearTracks.end(), [](const DatedTrack& a, const DatedTrack& b) {
                    if (a.favourite != b.favourite)
                        return a.favourite;
                    if (a.listens != b.listens)
                        return a.listens > b.listens;
                    if (a.exact != b.exact)
                        return a.exact;

                    // The id only settles a full tie, so that two runs of the same request cannot
                    // hand the client the same year in a different order.
                    return a.id < b.id;
                });

                Group group;
                group.year = year;
                group.exact = std::any_of(yearTracks.begin(), yearTracks.end(), [](const DatedTrack& track) { return track.exact; });
                group.total = yearTracks.size();

                for (const DatedTrack& track : yearTracks)
                {
                    if (group.trackIds.size() >= maxPerYear)
                        break;

                    group.trackIds.push_back(track.id);
                }

                groups.push_back(std::move(group));
            }

            return groups;
        }

        std::size_t clampWindowDays(std::size_t windowDays)
        {
            return std::min(windowDays, maxWindowDays);
        }

        std::size_t clampMaxPerYear(std::size_t maxPerYear)
        {
            return std::clamp(maxPerYear, std::size_t{ 1 }, maxMaxPerYear);
        }

        std::optional<Wt::WDate> parseIsoDate(std::string_view date)
        {
            const Wt::WDate parsed{ Wt::WDate::fromString(Wt::WString::fromUTF8(std::string{ date }), "yyyy-MM-dd") };
            if (!parsed.isValid())
                return std::nullopt;

            return parsed;
        }
    } // namespace memories

    namespace
    {
        /** The original release when the tags carry one, otherwise this edition's release date. */
        const core::PartialDateTime& effectiveDate(const db::Track::pointer& track)
        {
            return track->getOriginalDate().isValid() ? track->getOriginalDate() : track->getDate();
        }

        /**
         * The date the memories are relative to.
         *
         * Clients send their own local date, so that a device in another time zone gets its own
         * "today" rather than the server's.
         */
        Wt::WDate resolveRequestDate(RequestContext& ctx)
        {
            const auto date{ getParameterAs<std::string>(ctx.getParameters(), "date") };
            if (!date)
                return Wt::WDate::currentDate();

            const auto parsed{ memories::parseIsoDate(*date) };
            if (!parsed)
                throw RequiredParameterMissingError{ "date" };

            return *parsed;
        }
    } // namespace

    Response handleGetMemories(RequestContext& ctx)
    {
        auto& session{ ctx.getDbSession() };

        const Wt::WDate requestDate{ resolveRequestDate(ctx) };
        const std::size_t windowDays{ memories::clampWindowDays(getParameterAs<std::size_t>(ctx.getParameters(), "windowDays").value_or(memories::defaultWindowDays)) };
        const std::size_t maxPerYear{ memories::clampMaxPerYear(getParameterAs<std::size_t>(ctx.getParameters(), "maxPerYear").value_or(memories::defaultMaxPerYear)) };

        // Optional: one year's memories rather than every year's. A year nobody has memories in is
        // an empty answer, not an error, exactly as a day without memories is.
        const auto requestedYear{ getParameterAs<int>(ctx.getParameters(), "year") };

        auto transaction{ session.createReadTransaction() };

        db::Track::ReleaseAnniversaryParameters params;
        params.month = static_cast<unsigned>(requestDate.month());
        params.day = static_cast<unsigned>(requestDate.day());
        params.windowDays = static_cast<unsigned>(windowDays);
        params.currentYear = requestDate.year();

        const auto trackIds{ db::Track::findIdsByReleaseAnniversary(session, params) };

        std::vector<memories::DatedTrack> dated;
        std::unordered_map<db::TrackId, db::Track::pointer> tracksById;

        const db::UserId userId{ ctx.getUser()->getId() };

        for (const db::TrackId trackId : trackIds.results)
        {
            const db::Track::pointer track{ db::Track::find(session, trackId) };
            if (!track)
                continue;

            const core::PartialDateTime& date{ effectiveDate(track) };
            const auto year{ date.getYear() };
            if (!year)
                continue;

            // A client asking for one year pays for one year: the rating and the listen count are a
            // service call each, and there is no point spending them on years it will not show.
            if (requestedYear && *requestedYear != *year)
                continue;

            const bool exact{ date.getMonth() == static_cast<int>(params.month) && date.getDay() == static_cast<int>(params.day) };
            const auto rating{ core::Service<feedback::IFeedbackService>::get()->getRating(userId, trackId) };
            const std::size_t listens{ core::Service<scrobbling::IScrobblingService>::get()->getCount(userId, trackId) };

            dated.push_back({ trackId, *year, exact, rating.value_or(0) >= 5, listens });
            tracksById[trackId] = track;
        }

        Response response{ Response::createOkResponse(ctx.getServerProtocolVersion()) };
        auto& memoriesNode{ response.createNode("memories") };

        const std::vector<memories::Group> groups{ memories::groupByYear(dated, maxPerYear) };

        // An empty answer is a success, not an error: the array is always present so that clients
        // never have to distinguish "no memories today" from "this server has no such concept".
        if (groups.empty())
            memoriesNode.createEmptyArrayChild("memory");

        for (const memories::Group& group : groups)
        {
            Response::Node& memoryNode{ memoriesNode.createArrayChild("memory") };

            // Named rather than implied, so that a later "first listened" memory is an extra kind
            // instead of a breaking change.
            memoryNode.setAttribute("kind", "release");
            memoryNode.setAttribute("year", group.year);
            memoryNode.setAttribute("yearsAgo", requestDate.year() - group.year);
            memoryNode.setAttribute("exact", group.exact);

            // The year's own size, which is what a client counts out loud. The number of `song`
            // children below it is a page, and says how much of that year this answer carries.
            memoryNode.setAttribute("songCount", static_cast<int>(group.total));

            for (const db::TrackId trackId : group.trackIds)
                memoryNode.addArrayChild("song", createSongNode(ctx, tracksById.at(trackId), true));
        }

        return response;
    }
} // namespace lms::api::subsonic
