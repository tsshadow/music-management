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

#include "Spotify.hpp"

#include "../ParameterParsing.hpp"
#include "../RequestContext.hpp"
#include "../SubsonicId.hpp"
#include "core/String.hpp"
#include "database/Session.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/Listen.hpp"
#include "database/objects/Track.hpp"
#include "responses/Playlist.hpp"
#include "responses/Song.hpp"

namespace lms::api::subsonic
{
    Response handleGetSpotifyCuratedPlaylists(RequestContext& ctx)
    {
        auto& session{ ctx.getDbSession() };
        auto transaction{ session.createReadTransaction() };

        Response response{ Response::createOkResponse(ctx.getServerProtocolVersion()) };

        auto addPlaylist = [&](const std::string& id, const std::string& name, const std::string& description) {
            auto& node = response.createArrayNode("playlist");
            node.setAttribute("id", id);
            node.setAttribute("name", name);
            node.setAttribute("comment", description);
            node.setAttribute("owner", "LMS");
            node.setAttribute("public", true);
            node.setAttribute("songCount", 0);
            node.setAttribute("created", Wt::WDateTime::currentDateTime().toString().toUTF8());
        };

        // 1. Release Radar
        addPlaylist("spotify:release_radar", "Release Radar", "Recent releases and new discoveries.");

        // 2. Genre Playlists
        const std::vector<std::string> genres = {
            "mainstream hardstyle", "raw hardstyle", "mainstream hardcore", "uptempo hardcore",
            "zaagtempo", "krach", "industrial hardcore", "hardcore", "hardstyle", "frenchcore"
                                                                                  "euphoric frenchcore",
            "euphoric hardstyle", "terror"
        };

        for (const auto& genre : genres)
        {
            addPlaylist("spotify:genre:" + genre, genre, "Curated " + genre + " tracks.");
        }

        // 3. Sets
        addPlaylist("spotify:sets", "Sets & Mixes", "Sets and mixes");

        // 4. Songs
        addPlaylist("spotify:songs", "Songs", "All songs");

        return response;
    }

    std::optional<Response> handleGetSpotifyPlaylist(RequestContext& ctx, const std::string& id)
    {
        if (!id.starts_with("spotify:"))
            return std::nullopt;

        auto& session{ ctx.getDbSession() };
        auto transaction{ session.createReadTransaction() };

        db::Track::FindParameters params;
        std::string name;
        std::string description;

        if (id == "spotify:release_radar")
        {
            name = "Release Radar";
            description = "Recent releases and new discoveries.";
            params.maxDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::OriginalDateDescAndRelease);
            params.range = db::Range{ 0, 50 };
        }
        else if (id == "spotify:sets")
        {
            name = "Sets & Mixes";
            description = "Sets and mixes";
            params.minDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::Random);
            params.range = db::Range{ 0, 50 };
        }
        else if (id == "spotify:songs")
        {
            name = "Songs";
            description = "All songs";
            params.maxDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::Random);
            params.range = db::Range{ 0, 50 };
        }
        else if (id.starts_with("spotify:genre:"))
        {
            std::string genreName = id.substr(std::string("spotify:genre:").length());
            name = genreName;
            description = "Curated " + genreName + " tracks.";

            if (auto genreType = db::ClusterType::find(session, "GENRE"))
            {
                if (auto cluster = genreType->getCluster(genreName))
                {
                    params.filters.clusters.push_back(cluster->getId());
                }
            }
            params.maxDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::Random);
            params.range = db::Range{ 0, 50 };
        }
        else
        {
            return std::nullopt;
        }

        Response response{ Response::createOkResponse(ctx.getServerProtocolVersion()) };
        auto& playlistNode = response.createNode("playlist");
        playlistNode.setAttribute("id", id);
        playlistNode.setAttribute("name", name);
        playlistNode.setAttribute("comment", description);
        playlistNode.setAttribute("owner", "LMS");
        playlistNode.setAttribute("public", true);

        db::Track::find(session, params, [&](const db::Track::pointer& track) {
            playlistNode.addArrayChild("entry", createSongNode(ctx, track, true));
        });

        return response;
    }

    Response handleGetSpotifyPlaylistRequest(RequestContext& ctx)
    {
        auto id = getParameterAs<std::string>(ctx.getParameters(), "id");
        if (!id)
            throw RequiredParameterMissingError{ "id" };

        auto response = handleGetSpotifyPlaylist(ctx, *id);
        if (!response)
            throw RequestedDataNotFoundError{};

        return std::move(*response);
    }

    Response handleGetSpotifyTracks(RequestContext& ctx)
    {
        auto& session{ ctx.getDbSession() };
        auto transaction{ session.createReadTransaction() };

        db::Track::FindParameters params;

        if (auto artist = getParameterAs<std::string>(ctx.getParameters(), "artist"))
        {
            params.setArtistName(*artist, { db::TrackArtistLinkType::Artist });
        }

        if (auto artistId = getParameterAs<db::ArtistId>(ctx.getParameters(), "artistId"))
        {
            params.setArtist(*artistId, { db::TrackArtistLinkType::Artist });
        }

        if (auto genre = getParameterAs<std::string>(ctx.getParameters(), "genre"))
        {
            if (auto genreType = db::ClusterType::find(session, "GENRE"))
            {
                if (auto cluster = genreType->getCluster(*genre))
                {
                    params.filters.clusters.push_back(cluster->getId());
                }
            }
        }

        if (auto year = getParameterAs<std::string>(ctx.getParameters(), "year"))
        {
            if (auto yearType = db::ClusterType::find(session, "YEAR"))
            {
                if (auto cluster = yearType->getCluster(*year))
                {
                    params.filters.clusters.push_back(cluster->getId());
                }
            }
        }

        if (auto sort = getParameterAs<std::string>(ctx.getParameters(), "sort"))
        {
            if (*sort == "recent" || *sort == "releasedate")
                params.setSortMethod(db::TrackSortMethod::OriginalDateDescAndRelease);
            else if (*sort == "added")
                params.setSortMethod(db::TrackSortMethod::AddedDesc);
            else if (*sort == "random")
                params.setSortMethod(db::TrackSortMethod::Random);
            else if (*sort == "alpha" || *sort == "alphabetical")
                params.setSortMethod(db::TrackSortMethod::Name);
            else if (*sort == "starred")
                params.setStarringUser(ctx.getUser()->getId(), db::FeedbackBackend::Internal);
            else if (*sort == "mostplayed")
                params.setSortMethod(db::TrackSortMethod::MostPlayed);
            else if (*sort == "recentlyplayed")
                params.setSortMethod(db::TrackSortMethod::RecentlyPlayed);
            else if (*sort == "rating")
            {
                params.setSortMethod(db::TrackSortMethod::RatingDesc);
                params.ratingUser = ctx.getUser()->getId();
            }
        }

        auto query = getParameterAs<std::string>(ctx.getParameters(), "query");
        if (query && !query->empty())
        {
            params.setKeywords(core::stringUtils::splitString(*query, ' '));
        }

        if (auto minDuration = getParameterAs<int>(ctx.getParameters(), "minDuration"))
        {
            params.minDuration = std::chrono::minutes(*minDuration);
        }

        if (auto maxDuration = getParameterAs<int>(ctx.getParameters(), "maxDuration"))
        {
            params.maxDuration = std::chrono::minutes(*maxDuration);
        }

        if (auto minRating = getParameterAs<int>(ctx.getParameters(), "minRating"))
        {
            params.minRating = *minRating;
            params.ratingUser = ctx.getUser()->getId();
        }

        if (auto includeUnrated = getParameterAs<bool>(ctx.getParameters(), "includeUnrated"))
        {
            params.includeUnrated = *includeUnrated;
        }

        if (auto maxRating = getParameterAs<int>(ctx.getParameters(), "maxRating"))
        {
            params.maxRating = *maxRating;
            params.ratingUser = ctx.getUser()->getId();
        }

        int offset = getParameterAs<int>(ctx.getParameters(), "offset").value_or(0);
        int count = getParameterAs<int>(ctx.getParameters(), "count").value_or(50);
        params.range = db::Range{ static_cast<std::size_t>(offset), static_cast<std::size_t>(count) };

        Response response{ Response::createOkResponse(ctx.getServerProtocolVersion()) };
        auto& tracksNode = response.createNode("tracks");

        bool moreResults = false;
        db::Track::find(session, params, moreResults, [&](const db::Track::pointer& track) {
            tracksNode.addArrayChild("track", createSongNode(ctx, track, true));
        });

        tracksNode.setAttribute("moreResults", moreResults);

        return response;
    }

    Response handleGetSpotifyHistory(RequestContext& ctx)
    {
        auto& session{ ctx.getDbSession() };
        auto transaction{ session.createReadTransaction() };

        db::Listen::FindParameters params;
        params.setUser(ctx.getUser()->getId());
        params.setDesc(true);

        int offset = getParameterAs<int>(ctx.getParameters(), "offset").value_or(0);
        int count = getParameterAs<int>(ctx.getParameters(), "count").value_or(50);
        params.range = db::Range{ static_cast<std::size_t>(offset), static_cast<std::size_t>(count) };

        Response response{ Response::createOkResponse(ctx.getServerProtocolVersion()) };
        auto& historyNode = response.createNode("history");

        bool moreResults = false;
        db::Listen::find(session, params).forEach([&](db::ListenId listenId) {
            if (auto listen = db::Listen::find(session, listenId))
            {
                auto& entryNode = historyNode.addArrayChild("entry", createSongNode(ctx, listen->getTrack(), true));
                entryNode.setAttribute("listenedAt", listen->getDateTime().toString().toUTF8());
            }
        });

        return response;
    }
} // namespace lms::api::subsonic
