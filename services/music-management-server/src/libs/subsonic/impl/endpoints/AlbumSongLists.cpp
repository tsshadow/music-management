/*
 * Copyright (C) 2023 Emeric Poupon
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

#include "AlbumSongLists.hpp"

#include <algorithm>
#include <chrono>
#include <set>

#include "core/Service.hpp"
#include "core/String.hpp"
#include "database/Session.hpp"
#include "database/Types.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"
#include "rapidjson.h"
#include "services/feedback/IFeedbackService.hpp"
#include "services/scrobbling/IScrobblingService.hpp"

#include "FestivalLineupRepository.hpp"
#include "ParameterParsing.hpp"
#include "SubsonicId.hpp"
#include "TrackForm.hpp"
#include "document.h"
#include "responses/Album.hpp"
#include "responses/Artist.hpp"
#include "responses/Song.hpp"

namespace lms::api::subsonic
{
    using namespace db;

    namespace
    {
        Response handleGetAlbumListRequestCommon(RequestContext& context, bool id3)
        {
            // Mandatory params
            const std::string type{ getMandatoryParameterAs<std::string>(context.getParameters(), "type") };

            // Optional params
            const MediaLibraryId mediaLibraryId{ getParameterAs<MediaLibraryId>(context.getParameters(), "musicFolderId").value_or(MediaLibraryId{}) };
            const std::size_t size{ getParameterAs<std::size_t>(context.getParameters(), "size").value_or(10) };
            const std::size_t offset{ getParameterAs<std::size_t>(context.getParameters(), "offset").value_or(0) };
            const std::string query{ getParameterAs<std::string>(context.getParameters(), "query").value_or("") };
            if (size > defaultMaxCountSize)
                throw ParameterValueTooHighGenericError{ "size", defaultMaxCountSize };

            const Range range{ offset, size };

            // Backs the keywords below: FindParameters::keywords holds string_views into it, so it
            // must outlive every find call made with these parameters (one per branch of the type
            // chain below, all reusing this same keywords vector).
            const std::vector<std::string_view> keywords{ query.empty() ? std::vector<std::string_view>{} : core::stringUtils::splitString(query, ' ') };

            RangeResults<ReleaseId> releases;
            scrobbling::IScrobblingService::ArtistFindParameters artistFindParams; // Dummy for now, but maybe use keywords there too?
            scrobbling::IScrobblingService& scrobblingService{ *core::Service<scrobbling::IScrobblingService>::get() };
            feedback::IFeedbackService& feedbackService{ *core::Service<feedback::IFeedbackService>::get() };

            auto transaction{ context.getDbSession().createReadTransaction() };

            if (type == "alphabeticalByName" || type == "alphabetical")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::Name);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "alphabeticalByArtist" || type == "byArtist")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::ArtistNameThenName);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "byTrackCount")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::TrackCountDesc);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "byGenre")
            {
                // Mandatory param
                const std::string genre{ getMandatoryParameterAs<std::string>(context.getParameters(), "genre") };

                if (const ClusterType::pointer clusterType{ ClusterType::find(context.getDbSession(), "GENRE") })
                {
                    if (const Cluster::pointer cluster{ clusterType->getCluster(genre) })
                    {
                        Release::FindParameters params;
                        params.filters.setMediaLibrary(mediaLibraryId);
                        params.filters.setClusters(std::initializer_list<ClusterId>{ cluster->getId() });
                        params.setSortMethod(ReleaseSortMethod::Name);
                        params.setRange(range);
                        params.setKeywords(keywords);

                        releases = Release::findIds(context.getDbSession(), params);
                    }
                }
            }
            else if (type == "byYear" || type == "year")
            {
                const std::optional<int> fromYear{ getParameterAs<int>(context.getParameters(), "fromYear") };
                const std::optional<int> toYear{ getParameterAs<int>(context.getParameters(), "toYear") };

                Release::FindParameters params;
                if (fromYear && toYear)
                {
                    params.setSortMethod(*fromYear > *toYear ? ReleaseSortMethod::OriginalDateDesc : ReleaseSortMethod::OriginalDate);
                    params.setOriginalDateRange(YearRange{ std::min(*fromYear, *toYear), std::max(*fromYear, *toYear) });
                }
                else
                {
                    params.setSortMethod(ReleaseSortMethod::OriginalDateDesc);
                }
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "frequent")
            {
                scrobbling::IScrobblingService::FindParameters params;
                params.setUser(context.getUser()->getId());
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = scrobblingService.getTopReleases(params);
            }
            else if (type == "newest")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::AddedDesc);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "updated")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::LastWrittenDesc);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "random")
            {
                // Random results are paginated, but there is no acceptable way to handle the pagination params without repeating some albums
                // (no seed provided by subsonic, ot it would require to store some kind of context for each user/client when iterating over the random albums)
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::Random);
                params.setRange(Range{ 0, size });
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "recent")
            {
                scrobbling::IScrobblingService::FindParameters params;
                params.setUser(context.getUser()->getId());
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = scrobblingService.getRecentReleases(params);
            }
            else if (type == "starred")
            {
                feedback::IFeedbackService::FindParameters params;
                params.setUser(context.getUser()->getId());
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);
                params.setKeywords(keywords);

                releases = feedbackService.findFavoriteReleases(params);
            }
            else
            {
                throw NotImplementedGenericError{};
            }

            Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
            Response::Node& albumListNode{ response.createNode(id3 ? Response::Node::Key{ "albumList2" } : Response::Node::Key{ "albumList" }) };

            for (const ReleaseId releaseId : releases.results)
            {
                const Release::pointer release{ Release::find(context.getDbSession(), releaseId) };
                albumListNode.addArrayChild("album", createAlbumNode(context, release, id3));
            }

            return response;
        }

        Response handleGetStarredRequestCommon(RequestContext& context, bool id3)
        {
            // Optional parameters
            const MediaLibraryId mediaLibrary{ getParameterAs<MediaLibraryId>(context.getParameters(), "musicFolderId").value_or(MediaLibraryId{}) };

            auto transaction{ context.getDbSession().createReadTransaction() };

            Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
            Response::Node& starredNode{ response.createNode(id3 ? Response::Node::Key{ "starred2" } : Response::Node::Key{ "starred" }) };

            feedback::IFeedbackService& feedbackService{ *core::Service<feedback::IFeedbackService>::get() };

            // We don't support starring directories
            if (id3)
            {
                feedback::IFeedbackService::ArtistFindParameters artistFindParams;
                artistFindParams.setUser(context.getUser()->getId());
                artistFindParams.setSortMethod(ArtistSortMethod::SortName);
                for (const ArtistId artistId : feedbackService.findFavoriteArtists(artistFindParams).results)
                {
                    if (auto artist{ Artist::find(context.getDbSession(), artistId) })
                        starredNode.addArrayChild("artist", createArtistNode(context, artist));
                }
            }

            feedback::IFeedbackService::FindParameters findParameters;
            findParameters.setUser(context.getUser()->getId());
            findParameters.filters.setMediaLibrary(mediaLibrary);

            for (const ReleaseId releaseId : feedbackService.findFavoriteReleases(findParameters).results)
            {
                if (auto release{ Release::find(context.getDbSession(), releaseId) })
                    starredNode.addArrayChild("album", createAlbumNode(context, release, id3));
            }

            // One row per song (bug report 096): a favourite version stands for its song and is
            // shown as the canonical, once, at the place of its most recently rated version. Done
            // here rather than in the query because this list is not paged, so collapsing after
            // the fetch is exact; the canonical's rating is rolled up in createSongNode.
            std::set<TrackId> shown;
            for (const TrackId trackId : feedbackService.findFavoriteTracks(findParameters).results)
            {
                const Track::pointer track{ Track::findCanonicalVersion(context.getDbSession(), Track::find(context.getDbSession(), trackId)) };
                if (!track || !shown.insert(track->getId()).second)
                    continue;
                // The song is a favourite when the rating its row shows is: a canonical that was
                // itself rated lower overrides a favourite version, and must not be listed here
                // looking unstarred.
                if (track->getId() != trackId && !feedbackService.getSongRating(context.getUser()->getId(), track->getId()).favoriteDateTime.isValid())
                    continue;
                starredNode.addArrayChild("song", createSongNode(context, track, context.getUser()));
            }

            return response;
        }
    } // namespace

    Response handleGetAlbumListRequest(RequestContext& context)
    {
        return handleGetAlbumListRequestCommon(context, false /* no id3 */);
    }

    Response handleGetAlbumList2Request(RequestContext& context)
    {
        return handleGetAlbumListRequestCommon(context, true /* id3 */);
    }

    Response handleGetRandomSongsRequest(RequestContext& context)
    {
        // Optional params
        const MediaLibraryId mediaLibraryId{ getParameterAs<MediaLibraryId>(context.getParameters(), "musicFolderId").value_or(MediaLibraryId{}) };
        std::size_t size{ getParameterAs<std::size_t>(context.getParameters(), "size").value_or(50) };
        if (size > defaultMaxCountSize)
            throw ParameterValueTooHighGenericError{ "size", defaultMaxCountSize };

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& randomSongsNode{ response.createNode("randomSongs") };

        auto transaction{ context.getDbSession().createReadTransaction() };

        Track::FindParameters params;
        params.setSortMethod(TrackSortMethod::Random);
        params.setRange(Range{ 0, size });
        params.filters.setMediaLibrary(mediaLibraryId);
        // A shuffle draws songs, not files: two versions of one song are one draw (bug report 096).
        params.canonicalOnly = true;
        // And music: never an interview or a DVD preview (docs/designs/non-music-forms/).
        params.excludeNonMusic = true;

        Track::find(context.getDbSession(), params, [&](const Track::pointer& track) {
            randomSongsNode.addArrayChild("song", createSongNode(context, track, context.getUser()));
        });

        return response;
    }

    ClusterId GetCluster(std::string value, std::string name, RequestContext& context)
    {
        auto clusterType{ ClusterType::find(context.getDbSession(), name) };
        if (!clusterType)
            throw RequestedDataNotFoundError{};
        auto cluster{ clusterType->getCluster(value) };
        if (!cluster)
            throw RequestedDataNotFoundError{};
        return cluster->getId();
    }

    Response handleGetSongsByGenreRequest(RequestContext& context)
    {
        // Mandatory params
        std::string genre{ getMandatoryParameterAs<std::string>(context.getParameters(), "genre") };

        // Optional params
        std::optional<std::string> year{ getParameterAs<std::string>(context.getParameters(), "year") };
        std::optional<std::string> length{ getParameterAs<std::string>(context.getParameters(), "length") };
        const MediaLibraryId mediaLibrary{ getParameterAs<MediaLibraryId>(context.getParameters(), "musicFolderId").value_or(MediaLibraryId{}) };
        std::size_t count{ getParameterAs<std::size_t>(context.getParameters(), "count").value_or(10) };
        std::size_t ratingMin{ getParameterAs<std::size_t>(context.getParameters(), "ratingMin").value_or(0) };
        std::size_t ratingMax{ getParameterAs<std::size_t>(context.getParameters(), "ratingMax").value_or(5) };
        if (count > defaultMaxCountSize)
            throw ParameterValueTooHighGenericError{ "count", defaultMaxCountSize };

        std::size_t offset{ getParameterAs<std::size_t>(context.getParameters(), "offset").value_or(0) };

        auto transaction{ context.getDbSession().createReadTransaction() };

        auto clusterType{ ClusterType::find(context.getDbSession(), "GENRE") };
        if (!clusterType)
            throw RequestedDataNotFoundError{};

        auto cluster{ clusterType->getCluster(genre) };
        if (!cluster)
            throw RequestedDataNotFoundError{};

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& songsByGenreNode{ response.createNode("songsByGenre") };

        Track::FindParameters params;
        std::vector<ClusterId> clusters = { cluster->getId() };
        if (year.has_value())
        {
            clusters.push_back(GetCluster(year.value(), "YEAR", context));
        }
        if (length.has_value())
        {
            clusters.push_back(GetCluster(length.value(), "LENGTH", context));
        }
        params.filters.setClusters(clusters);
        params.filters.setMediaLibrary(mediaLibrary);
        params.setRange(Range{ offset, count });
        // A genre lists its music, not the interviews filed under it.
        params.excludeNonMusic = true;
        params.setMinRating(static_cast<int>(ratingMin));
        params.setMaxRating(static_cast<int>(ratingMax));
        params.ratingUser = context.getUser()->getId();
        params.includeUnrated = true;
        // A genre list shows songs, not files (bug report 096).
        params.canonicalOnly = true;

        Track::find(context.getDbSession(), params, [&](const Track::pointer& track) {
            songsByGenreNode.addArrayChild("song", createSongNode(context, track, context.getUser()));
        });

        return response;
    }

    Response handleGetSongsByFilterRequest(RequestContext& context)
    {
        // Every parameter is optional: with none of them set this is getRandomSongs.
        // Radio channels are stored filters, and they all come through here.
        const std::optional<std::string> label{ getParameterAs<std::string>(context.getParameters(), "label") };
        const std::optional<std::string> genre{ getParameterAs<std::string>(context.getParameters(), "genre") };
        const std::optional<std::string> year{ getParameterAs<std::string>(context.getParameters(), "year") };
        const std::optional<std::string> length{ getParameterAs<std::string>(context.getParameters(), "length") };
        const std::optional<std::string> artist{ getParameterAs<std::string>(context.getParameters(), "artist") };
        const std::optional<int> ratingMin{ getParameterAs<int>(context.getParameters(), "ratingMin") };
        const std::optional<int> ratingMax{ getParameterAs<int>(context.getParameters(), "ratingMax") };
        // Seconds, unlike getSongs' minDuration/maxDuration which are minutes -- hence the
        // different names. A radio channel wants "under four minutes", not "under four".
        const std::optional<int> durationMin{ getParameterAs<int>(context.getParameters(), "durationMin") };
        const std::optional<int> durationMax{ getParameterAs<int>(context.getParameters(), "durationMax") };
        // A rating filter selects on ratings, so unrated tracks are out unless asked for.
        const bool includeUnrated{ getParameterAs<bool>(context.getParameters(), "includeUnrated").value_or(false) };
        const MediaLibraryId mediaLibrary{ getParameterAs<MediaLibraryId>(context.getParameters(), "musicFolderId").value_or(MediaLibraryId{}) };
        const std::size_t count{ getParameterAs<std::size_t>(context.getParameters(), "count").value_or(20) };
        if (count > defaultMaxCountSize)
            throw ParameterValueTooHighGenericError{ "count", defaultMaxCountSize };
        const std::size_t offset{ getParameterAs<std::size_t>(context.getParameters(), "offset").value_or(0) };
        const std::optional<int> seed{ getParameterAs<int>(context.getParameters(), "seed") };

        auto transaction{ context.getDbSession().createReadTransaction() };

        Track::FindParameters params;
        params.setSortMethod(TrackSortMethod::Random);
        params.setRange(Range{ offset, count });
        params.filters.setMediaLibrary(mediaLibrary);
        if (seed.has_value())
            params.randomSeed = seed;
        // A radio channel plays songs, not files (bug report 096), like getRandomSongs above,
        // and only music.
        params.canonicalOnly = true;
        params.excludeNonMusic = true;

        std::vector<ClusterId> clusters;
        if (genre.has_value())
            clusters.push_back(GetCluster(genre.value(), "GENRE", context));
        if (year.has_value())
            clusters.push_back(GetCluster(year.value(), "YEAR", context));
        if (length.has_value())
            clusters.push_back(GetCluster(length.value(), "LENGTH", context));
        if (!clusters.empty())
            params.filters.setClusters(clusters);

        if (label.has_value())
        {
            // Named rather than by id: the caller stores a channel, not a database row,
            // and the name survives a rescan.
            const Label::pointer labelObject{ Label::find(context.getDbSession(), label.value()) };
            if (!labelObject)
                throw RequestedDataNotFoundError{};
            params.filters.setLabel(labelObject->getId());
        }

        if (artist.has_value())
            params.setArtistName(artist.value());

        if (ratingMin.has_value() || ratingMax.has_value())
        {
            params.ratingUser = context.getUser()->getId();
            params.includeUnrated = includeUnrated;
            if (ratingMin.has_value())
                params.setMinRating(ratingMin.value());
            if (ratingMax.has_value())
                params.setMaxRating(ratingMax.value());
        }

        if (durationMin.has_value())
            params.minDuration = std::chrono::seconds{ durationMin.value() };
        if (durationMax.has_value())
            params.maxDuration = std::chrono::seconds{ durationMax.value() };

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& songsByFilterNode{ response.createNode("songsByFilter") };

        Track::find(context.getDbSession(), params, [&](const Track::pointer& track) {
            songsByFilterNode.addArrayChild("song", createSongNode(context, track, context.getUser()));
        });

        return response;
    }

    Response handleGetNowPlayingRequest(RequestContext& context)
    {
        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& nowPlayingNode{ response.createNode("nowPlaying") };

        scrobbling::IScrobblingService& scrobblingService{ *core::Service<scrobbling::IScrobblingService>::get() };

        const auto now{ scrobbling::IScrobblingService::Clock::now() };

        scrobblingService.visitNowPlayingListens([&](scrobbling::IScrobblingService::Clock::time_point startedAt, const scrobbling::Listen& listen) {
            auto transaction{ context.getDbSession().createReadTransaction() };

            // A regular user can only see his own now playing entry
            if (!context.getUser()->isAdmin() && listen.userId != context.getUser()->getId())
                return;

            const User::pointer user{ User::find(context.getDbSession(), listen.userId) };
            if (!user)
                return;

            const Track::pointer track{ Track::find(context.getDbSession(), listen.trackId) };
            if (!track)
                return;

            auto NowPlayingEntryNode{ createSongNode(context, track, context.getUser()) };
            NowPlayingEntryNode.setAttribute("username", user->getLoginName());
            NowPlayingEntryNode.setAttribute("minutesAgo", static_cast<int>(std::chrono::duration_cast<std::chrono::minutes>(now - startedAt).count()));
            NowPlayingEntryNode.setAttribute("playerId", user->getId().getValue()); // not sure what to put here

            nowPlayingNode.addArrayChild("song", std::move(NowPlayingEntryNode));
        });

        return response;
    }

    static std::map<std::string, std::set<ClusterId>> parseClusterGroups(const std::string& json, RequestContext& context)
    {
        std::map<std::string, std::set<ClusterId>> clusterGroups;

        rapidjson::Document document;
        document.Parse(json.c_str());

        if (document.HasParseError() || !document.IsArray())
            throw ParameterJsonFailedToParse{ json };

        for (const auto& filter : document.GetArray())
        {
            // Validate expected structure
            if (!filter.IsObject() || !filter.HasMember("name") || !filter.HasMember("value"))
                throw ParameterJsonFailedToParse{ json };

            const auto& nameValue = filter["name"];
            const auto& value = filter["value"];

            if (!nameValue.IsString())
                throw ParameterJsonFailedToParse{ json };

            const std::string name = nameValue.GetString();
            auto& clusterSet = clusterGroups[name];

            if (value.IsArray())
            {
                for (const auto& val : value.GetArray())
                {
                    if (val.IsString())
                        clusterSet.insert(GetCluster(val.GetString(), name, context));
                    else if (val.IsInt())
                        clusterSet.insert(GetCluster(std::to_string(val.GetInt()), name, context));
                    else
                        throw ParameterJsonFailedToParse{ json };
                }
            }
            else if (value.IsString())
            {
                clusterSet.insert(GetCluster(value.GetString(), name, context));
            }
            else if (value.IsInt())
            {
                clusterSet.insert(GetCluster(std::to_string(value.GetInt()), name, context));
            }
            else
            {
                throw ParameterJsonFailedToParse{ json };
            }
        }

        return clusterGroups;
    }

    /**
     * Handle songs endpoint
     *
     * The `clusters` query parameter should be a JSON-encoded array of filter objects.
     * Each filter object must include a `name` (e.g. "genre", "year") and a `value`.
     *
     * ✅ Supported value types:
     * - Single string:        "Hardcore"
     * - Single number:        2024
     * - Array of strings:     ["Hardcore", "Frenchcore"]
     * - Array of numbers:     [2023, 2024]
     *
     * 🔀 Each value array is interpreted as an OR condition.
     * 🧩 Multiple filters are combined using AND.
     *
     * ✅ Examples:
     * clusters=[
     *   {
     *     "name": "genre",
     *     "value": "Hardcore"
     *   },
     *   {
     *     "name": "year",
     *     "value": [2023, 2024]
     *   }
     * ]
     *
     * This would match tracks where:
     *   (genre == "Hardcore") AND (year == 2023 OR 2024)
     *
     * @param context RequestContext with parameters
     * @return Response with filtered songs
     */
    Response handleGetSongs(RequestContext& context)
    {
        // Optional query parameters
        auto filters = getParameterAs<std::string>(context.getParameters(), "clusters");
        auto sortMethod = stringToSortMethod(getParameterAs<std::string>(context.getParameters(), "sortMethod").value_or("AddedDesc"));
        MediaLibraryId const mediaLibraryId = getParameterAs<MediaLibraryId>(context.getParameters(), "musicFolderId").value_or(MediaLibraryId{});
        std::size_t size = getParameterAs<std::size_t>(context.getParameters(), "count").value_or(50);
        std::size_t const offset = getParameterAs<std::size_t>(context.getParameters(), "offset").value_or(0);
        std::optional<int> minRating = getParameterAs<int>(context.getParameters(), "ratingMin");
        std::optional<int> maxRating = getParameterAs<int>(context.getParameters(), "ratingMax");
        std::optional<std::string> festivalLineup = getParameterAs<std::string>(context.getParameters(), "festivalLineup");
        std::optional<int> minDuration = getParameterAs<int>(context.getParameters(), "minDuration");
        std::optional<int> maxDuration = getParameterAs<int>(context.getParameters(), "maxDuration");
        const std::vector<ArtistId> artistIds{ getMultiParametersAs<ArtistId>(context.getParameters(), "artistId") };
        // Every version of one song, for the list behind a track in the app. The same filter
        // getSpotifyTracks takes: the app browses through this endpoint, and a version list
        // that only the web can ask for would leave the phone showing a canonical it cannot
        // look past.
        const std::optional<int> workId{ getParameterAs<int>(context.getParameters(), "workId") };
        // One row per song rather than one per file. Off unless asked: every existing client
        // browses this endpoint and none of them expects rows to disappear.
        const bool canonicalOnly{ getParameterAs<bool>(context.getParameters(), "canonicalOnly").value_or(false) };
        // What muma classified the track as, and the year it files under (performance date for a
        // live set, else the date tag) -- the same two filters getSpotifyTracks takes, so the car
        // and voice can ask what the web asks. The YEAR cluster keeps its tag-year meaning.
        std::vector<std::string> forms{ parseTrackForms(context.getParameters()) };
        const std::optional<int> year{ getParameterAs<int>(context.getParameters(), "year") };
        // The seed of a Random sort, as getSongsByFilter and getSpotifyTracks take it: the same
        // seed answers the same shuffle, so offset pages through one order instead of drawing a
        // new one per page. The web's presets and the car's queue continuation page with it.
        const std::optional<int> seed{ getParameterAs<int>(context.getParameters(), "seed") };

        size = std::min(size, defaultMaxCountSize);

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        auto transaction = context.getDbSession().createReadTransaction();

        Track::FindParameters params;
        params.setSortMethod(sortMethod);
        params.setRange(Range{ offset, size });
        params.filters.setMediaLibrary(mediaLibraryId);
        params.workId = workId;
        // Asking for one song's versions and collapsing to one of them are opposites, so the
        // filter never applies when a workId was named.
        params.canonicalOnly = canonicalOnly && !workId.has_value();
        params.forms = std::move(forms);
        params.year = year;
        params.randomSeed = seed;
        // The app's songs and sets lists, the car and voice: music only. A non-music form named
        // in `form` still lists those (docs/designs/non-music-forms/).
        params.excludeNonMusic = true;

        std::map<std::string, std::set<ClusterId>> clusterGroups;
        if (filters.has_value())
        {
            clusterGroups = parseClusterGroups(filters.value(), context);
        }

        if (festivalLineup.has_value())
        {
            params.setAllowedArtists(FestivalLineupRepository::getArtistsForFestival(festivalLineup.value()));
        }

        if (minRating)
        {
            params.setMinRating(*minRating);
            params.ratingUser = context.getUser()->getId();
            params.includeUnrated = true;
        }
        if (maxRating)
        {
            params.setMaxRating(*maxRating);
            params.ratingUser = context.getUser()->getId();
        }
        if (minDuration)
        {
            params.minDuration = std::chrono::minutes(*minDuration);
        }
        if (maxDuration)
        {
            params.maxDuration = std::chrono::minutes(*maxDuration);
        }
        if (!artistIds.empty())
        {
            // A set: asking for the same artist twice must not turn into a self-join that
            // still means "this one artist".
            params.setArtists(std::set<ArtistId>{ artistIds.begin(), artistIds.end() },
                              { TrackArtistLinkType::Artist });
        }

        Response::Node& songsNode = response.createNode("songs");
        songsNode.setAttribute("totalCount", Track::countAdvanced(context.getDbSession(), params, clusterGroups));

        Track::find_advanced(context.getDbSession(), params, clusterGroups, [&](const Track::pointer& track) {
            songsNode.addArrayChild("song", createSongNode(context, track, context.getUser()));
        });

        return response;
    }

    Response handleGetSongSortMethods(RequestContext& context)
    {
        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& sortMethods{ response.createNode("sortMethods") };

        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::Id));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::Name));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::Random));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::AddedDesc));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::DateDescAndRelease));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::LastWrittenDesc));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::Release));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::TrackList));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::StarredDateDesc));
        sortMethods.addArrayValue("sortMethods", sortMethodToString(TrackSortMethod::None));

        return response;
    }

    Response handleGetLineups(RequestContext& context)
    {
        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& lineupsNodes = response.createNode("lineups");

        const auto keys = FestivalLineupRepository::getAllLineups();

        for (const auto& key : keys)
        {
            Response::Node lineupNode;
            lineupNode.setAttribute("name", key);
            lineupsNodes.addArrayChild("lineup", std::move(lineupNode));
        }

        return response;
    }
    Response handleGetStarredRequest(RequestContext& context)
    {
        return handleGetStarredRequestCommon(context, false /* no id3 */);
    }

    Response handleGetStarred2Request(RequestContext& context)
    {
        return handleGetStarredRequestCommon(context, true /* id3 */);
    }

} // namespace lms::api::subsonic
