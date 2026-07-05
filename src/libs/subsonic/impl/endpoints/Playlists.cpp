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

#include "Playlists.hpp"
#include "Spotify.hpp"

#include "database/Session.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackList.hpp"
#include "database/objects/User.hpp"
#include "database/objects/Cluster.hpp"

#include "ParameterParsing.hpp"
#include "SubsonicId.hpp"
#include "responses/Playlist.hpp"
#include "responses/Song.hpp"

#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>

#include "core/Service.hpp"
#include "services/feedback/IFeedbackService.hpp"

namespace lms::api::subsonic
{
    using namespace db;

    namespace
    {
        void checkTrackListModificationAccess(const db::TrackList::pointer& trackList, const db::UserId currentUserId)
        {
            if (!trackList || (trackList->getType() != TrackListType::PlayList && trackList->getType() != TrackListType::SmartPlaylist))
                throw RequestedDataNotFoundError{};

            // Can only modify own playlists
            if (trackList->getUserId() != currentUserId)
            {
                if (trackList->getVisibility() == TrackList::Visibility::Public)
                    throw UserNotAuthorizedError{};

                throw RequestedDataNotFoundError{};
            }
        }

        void resolveSmartPlaylist(RequestContext& context, const db::TrackList::pointer& trackList, std::vector<db::Track::pointer>& results)
        {
            if (trackList->getType() != TrackListType::SmartPlaylist || trackList->getSmartParams().empty())
                return;

            Wt::Json::Object root;
            Wt::Json::ParseError error;
            if (!Wt::Json::parse(std::string{ trackList->getSmartParams() }, root, error))
                return;

            Track::FindParameters params;
            
            // Limit
            params.range = Range{ 0, static_cast<std::size_t>(root.get("size").toNumber().orIfNull(50.0)) };

            // Sort Method
            if (auto sortMethod = root.get("sortMethod").toString(); !sortMethod.isNull())
                params.sortMethod = stringToSortMethod(sortMethod.orIfNull(""));

            // Genre
            if (const auto& genreVal = root.get("genre"); !genreVal.isNull())
            {
                std::vector<std::string> genres;
                if (genreVal.type() == Wt::Json::Type::Array)
                {
                    for (const auto& g : static_cast<const Wt::Json::Array&>(genreVal))
                        genres.push_back(g.toString().orIfNull(""));
                }
                else
                {
                    genres.push_back(genreVal.toString().orIfNull(""));
                }

                if (!genres.empty())
                {
                    if (const db::ClusterType::pointer genreType{ db::ClusterType::find(context.getDbSession(), "GENRE") })
                    {
                        for (const std::string& genreName : genres)
                        {
                            if (const auto cluster{ genreType->getCluster(genreName) })
                                params.filters.clusters.push_back(cluster->getId());
                        }
                    }
                }
            }

            // Artists
            if (const auto& artistsVal = root.get("artists"); !artistsVal.isNull())
            {
                 if (artistsVal.type() == Wt::Json::Type::Array && !static_cast<const Wt::Json::Array&>(artistsVal).empty())
                     params.artistName = static_cast<const Wt::Json::Array&>(artistsVal)[0].toString().orIfNull("");
                 else
                     params.artistName = artistsVal.toString().orIfNull("");
            }

            // Year
            if (const auto& yearVal = root.get("year"); !yearVal.isNull())
            {
                 std::string year;
                 if (yearVal.type() == Wt::Json::Type::Array && !static_cast<const Wt::Json::Array&>(yearVal).empty())
                     year = static_cast<const Wt::Json::Array&>(yearVal)[0].toString().orIfNull("");
                 else
                     year = yearVal.toString().orIfNull("");
                 
                 if (!year.empty())
                     params.keywords.push_back(year);
            }

            Track::find(context.getDbSession(), params, [&](const Track::pointer& track) {
                results.push_back(track);
            });
        }
    } // namespace

    Response handleGetPlaylistsRequest(RequestContext& context)
    {
        auto transaction{ context.getDbSession().createReadTransaction() };

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& playlistsNode{ response.createNode("playlists") };

        auto addTrackList{ [&](const db::TrackList::pointer& trackList) {
            playlistsNode.addArrayChild("playlist", createPlaylistNode(context, trackList));
        } };

        // First add user's playlists
        {
            TrackList::FindParameters params;
            params.setUser(context.getUser()->getId());

            db::TrackList::find(context.getDbSession(), params, [&](const db::TrackList::pointer& trackList) {
                if (trackList->getType() == TrackListType::PlayList || trackList->getType() == TrackListType::SmartPlaylist)
                    addTrackList(trackList);
            });
        }

        // Then add others public playlists
        {
            TrackList::FindParameters params;
            params.setVisibility(TrackList::Visibility::Public);
            params.setExcludedUser(context.getUser()->getId());

            db::TrackList::find(context.getDbSession(), params, [&](const db::TrackList::pointer& trackList) {
                assert(trackList->getUserId() != context.getUser()->getId());
                if (trackList->getType() == TrackListType::PlayList || trackList->getType() == TrackListType::SmartPlaylist)
                    addTrackList(trackList);
            });
        }

        return response;
    }

    Response handleGetPlaylistRequest(RequestContext& context)
    {
        // Mandatory params
        const auto id{ getParameterAs<std::string>(context.getParameters(), "id") };
        if (!id)
            throw RequiredParameterMissingError{ "id" };

        if (id->starts_with("spotify:"))
        {
            if (auto response = handleGetSpotifyPlaylist(context, *id))
                return std::move(*response);
        }

        TrackListId trackListId{ getMandatoryParameterAs<TrackListId>(context.getParameters(), "id") };

        auto transaction{ context.getDbSession().createReadTransaction() };

        TrackList::pointer trackList{ TrackList::find(context.getDbSession(), trackListId) };
        if (!trackList || (trackList->getType() != TrackListType::PlayList && trackList->getType() != TrackListType::SmartPlaylist))
            throw RequestedDataNotFoundError{};

        if (trackList->getUserId() != context.getUser()->getId() && trackList->getVisibility() != TrackList::Visibility::Public)
            throw RequestedDataNotFoundError{};

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node playlistNode{ createPlaylistNode(context, trackList) };

        if (trackList->getType() == TrackListType::SmartPlaylist)
        {
            std::vector<Track::pointer> tracks;
            resolveSmartPlaylist(context, trackList, tracks);
            for (const Track::pointer& track : tracks)
                playlistNode.addArrayChild("entry", createSongNode(context, track, context.getUser()));
        }
        else
        {
            auto entries{ trackList->getEntries() };
            for (const TrackListEntry::pointer& entry : entries.results)
                playlistNode.addArrayChild("entry", createSongNode(context, entry->getTrack(), context.getUser()));
        }

        response.addNode("playlist", std::move(playlistNode));

        return response;
    }

    Response handleCreatePlaylistRequest(RequestContext& context)
    {
        // Optional params
        const auto id{ getParameterAs<TrackListId>(context.getParameters(), "playlistId") };
        auto name{ getParameterAs<std::string>(context.getParameters(), "name") };

        std::vector<TrackId> trackIds{ getMultiParametersAs<TrackId>(context.getParameters(), "songId") };

        if (!name && !id)
            throw RequiredParameterMissingError{ "name or playlistId" };

        auto transaction{ context.getDbSession().createWriteTransaction() };

        TrackList::pointer trackList;
        if (id)
        {
            trackList = TrackList::find(context.getDbSession(), *id);
            checkTrackListModificationAccess(trackList, context.getUser()->getId());

            if (name)
                trackList.modify()->setName(*name);

            trackList.modify()->clear();
            trackList.modify()->setLastModifiedDateTime(Wt::WDateTime::currentDateTime());
        }
        else
        {
            trackList = context.getDbSession().create<TrackList>(*name, TrackListType::PlayList);
            trackList.modify()->setUser(context.getUser());
            trackList.modify()->setVisibility(TrackList::Visibility::Private);
        }

        for (const TrackId trackId : trackIds)
        {
            Track::pointer track{ Track::find(context.getDbSession(), trackId) };
            if (!track)
                continue;

            context.getDbSession().create<TrackListEntry>(track, trackList);
        }

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node playlistNode{ createPlaylistNode(context, trackList) };

        auto entries{ trackList->getEntries() };
        for (const TrackListEntry::pointer& entry : entries.results)
            playlistNode.addArrayChild("entry", createSongNode(context, entry->getTrack(), context.getUser()));

        response.addNode("playlist", std::move(playlistNode));

        return response;
    }

    Response handleUpdatePlaylistRequest(RequestContext& context)
    {
        // Mandatory params
        TrackListId id{ getMandatoryParameterAs<TrackListId>(context.getParameters(), "playlistId") };

        // Optional parameters
        auto name{ getParameterAs<std::string>(context.getParameters(), "name") };
        auto isPublic{ getParameterAs<bool>(context.getParameters(), "public") };

        std::vector<TrackId> trackIdsToAdd{ getMultiParametersAs<TrackId>(context.getParameters(), "songIdToAdd") };
        std::vector<std::size_t> trackPositionsToRemove{ getMultiParametersAs<std::size_t>(context.getParameters(), "songIndexToRemove") };

        auto transaction{ context.getDbSession().createWriteTransaction() };

        TrackList::pointer trackList{ TrackList::find(context.getDbSession(), id) };
        checkTrackListModificationAccess(trackList, context.getUser()->getId());

        if (name)
            trackList.modify()->setName(*name);

        trackList.modify()->setVisibility(isPublic ? db::TrackList::Visibility::Public : db::TrackList::Visibility::Private);
        trackList.modify()->setLastModifiedDateTime(Wt::WDateTime::currentDateTime());

        {
            // Remove from end to make indexes stable
            std::sort(std::begin(trackPositionsToRemove), std::end(trackPositionsToRemove), std::greater<std::size_t>());

            for (std::size_t trackPositionToRemove : trackPositionsToRemove)
            {
                auto entry{ trackList->getEntry(trackPositionToRemove) };
                if (entry)
                    entry.remove();
            }
        }

        // Add tracks
        for (const TrackId trackIdToAdd : trackIdsToAdd)
        {
            Track::pointer track{ Track::find(context.getDbSession(), trackIdToAdd) };
            if (!track)
                continue;

            context.getDbSession().create<TrackListEntry>(track, trackList);
        }

        return Response::createOkResponse(context.getServerProtocolVersion());
    }

    Response handleDeletePlaylistRequest(RequestContext& context)
    {
        TrackListId id{ getMandatoryParameterAs<TrackListId>(context.getParameters(), "id") };

        auto transaction{ context.getDbSession().createWriteTransaction() };

        TrackList::pointer trackList{ TrackList::find(context.getDbSession(), id) };
        checkTrackListModificationAccess(trackList, context.getUser()->getId());

        trackList.remove();

        return Response::createOkResponse(context.getServerProtocolVersion());
    }

    Response handleCreateDynamicPlaylistRequest(RequestContext& context)
    {
        auto name{ getMandatoryParameterAs<std::string>(context.getParameters(), "name") };
        auto smartParams{ getMandatoryParameterAs<std::string>(context.getParameters(), "smartParams") };

        TrackList::pointer trackList;
        {
            auto transaction{ context.getDbSession().createWriteTransaction() };

            trackList = context.getDbSession().create<TrackList>(name, TrackListType::SmartPlaylist);
            trackList.modify()->setSmartParams(smartParams);
            trackList.modify()->setUser(context.getUser());
            trackList.modify()->setVisibility(TrackList::Visibility::Private);
        }

        core::Service<feedback::IFeedbackService>::get()->notifyPlaylistChanged(trackList->getId());

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        response.addNode("playlist", createPlaylistNode(context, trackList));

        return response;
    }

    Response handleUpdateDynamicPlaylistRequest(RequestContext& context)
    {
        TrackListId id{ getMandatoryParameterAs<TrackListId>(context.getParameters(), "playlistId") };
        auto name{ getParameterAs<std::string>(context.getParameters(), "name") };
        auto smartParams{ getParameterAs<std::string>(context.getParameters(), "smartParams") };

        TrackList::pointer trackList;
        {
            auto transaction{ context.getDbSession().createWriteTransaction() };

            trackList = TrackList::find(context.getDbSession(), id);
            checkTrackListModificationAccess(trackList, context.getUser()->getId());

            if (name)
                trackList.modify()->setName(*name);
            if (smartParams)
                trackList.modify()->setSmartParams(*smartParams);

            trackList.modify()->setLastModifiedDateTime(Wt::WDateTime::currentDateTime());
        }

        core::Service<feedback::IFeedbackService>::get()->notifyPlaylistChanged(trackList->getId());

        return Response::createOkResponse(context.getServerProtocolVersion());
    }
} // namespace lms::api::subsonic
