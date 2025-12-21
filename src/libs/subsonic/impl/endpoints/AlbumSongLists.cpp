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

#include "core/Service.hpp"
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
            if (size > defaultMaxCountSize)
                throw ParameterValueTooHighGenericError{ "size", defaultMaxCountSize };

            const Range range{ offset, size };

            RangeResults<ReleaseId> releases;
            scrobbling::IScrobblingService& scrobblingService{ *core::Service<scrobbling::IScrobblingService>::get() };
            feedback::IFeedbackService& feedbackService{ *core::Service<feedback::IFeedbackService>::get() };

            auto transaction{ context.getDbSession().createReadTransaction() };

            if (type == "alphabeticalByName")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::Name);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "alphabeticalByArtist")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::ArtistNameThenName);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);

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

                        releases = Release::findIds(context.getDbSession(), params);
                    }
                }
            }
            else if (type == "byYear")
            {
                const int fromYear{ getMandatoryParameterAs<int>(context.getParameters(), "fromYear") };
                const int toYear{ getMandatoryParameterAs<int>(context.getParameters(), "toYear") };

                Release::FindParameters params;
                params.setSortMethod(fromYear > toYear ? ReleaseSortMethod::DateDesc : ReleaseSortMethod::DateAsc);
                params.setRange(range);
                params.setDateRange(YearRange{ std::min(fromYear, toYear), std::max(fromYear, toYear) });
                params.filters.setMediaLibrary(mediaLibraryId);

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "frequent")
            {
                scrobbling::IScrobblingService::FindParameters params;
                params.setUser(context.getUser()->getId());
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);

                releases = scrobblingService.getTopReleases(params);
            }
            else if (type == "newest")
            {
                Release::FindParameters params;
                params.setSortMethod(ReleaseSortMethod::AddedDesc);
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);

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

                releases = Release::findIds(context.getDbSession(), params);
            }
            else if (type == "recent")
            {
                scrobbling::IScrobblingService::FindParameters params;
                params.setUser(context.getUser()->getId());
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);

                releases = scrobblingService.getRecentReleases(params);
            }
            else if (type == "starred")
            {
                feedback::IFeedbackService::FindParameters params;
                params.setUser(context.getUser()->getId());
                params.setRange(range);
                params.filters.setMediaLibrary(mediaLibraryId);

                releases = feedbackService.findStarredReleases(params);
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
                for (const ArtistId artistId : feedbackService.findStarredArtists(artistFindParams).results)
                {
                    if (auto artist{ Artist::find(context.getDbSession(), artistId) })
                        starredNode.addArrayChild("artist", createArtistNode(context, artist));
                }
            }

            feedback::IFeedbackService::FindParameters findParameters;
            findParameters.setUser(context.getUser()->getId());
            findParameters.filters.setMediaLibrary(mediaLibrary);

            for (const ReleaseId releaseId : feedbackService.findStarredReleases(findParameters).results)
            {
                if (auto release{ Release::find(context.getDbSession(), releaseId) })
                    starredNode.addArrayChild("album", createAlbumNode(context, release, id3));
            }

            for (const TrackId trackId : feedbackService.findStarredTracks(findParameters).results)
            {
                if (auto track{ Track::find(context.getDbSession(), trackId) })
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
        params.setMinRating(static_cast<int>(ratingMin));
        params.setMaxRating(static_cast<int>(ratingMax));

        Track::find(context.getDbSession(), params, [&](const Track::pointer& track) {
            songsByGenreNode.addArrayChild("song", createSongNode(context, track, context.getUser()));
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

        size = std::min(size, defaultMaxCountSize);

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        auto transaction = context.getDbSession().createReadTransaction();

        Track::FindParameters params;
        params.setSortMethod(sortMethod);
        params.setRange(Range{ offset, size });
        params.filters.setMediaLibrary(mediaLibraryId);

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
        }
        if (maxRating)
        {
            params.setMaxRating(*maxRating);
        }

        Response::Node& songsNode = response.createNode("songs");

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