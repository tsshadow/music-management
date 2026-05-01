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

#include "database/Session.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/Track.hpp"
#include "../RequestContext.hpp"
#include "responses/Song.hpp"
#include "responses/Playlist.hpp"

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
            "zaagtempi", "krach", "industrial hardcore", "hardcore", "hardstyle",
            "euphoric frenchcore", "euphoric hardstyle", "terror"
        };

        for (const auto& genre : genres)
        {
            addPlaylist("spotify:genre:" + genre, genre, "Curated " + genre + " tracks.");
        }
        
        // 3. Sets
        addPlaylist("spotify:sets", "Sets & Mixes", "Long tracks (> 10 minutes)");

        return response;
    }

    Response handleGetSpotifyPlaylist(RequestContext& ctx)
    {
        auto id = ctx.getQueryParameter("id");
        if (!id || !id->starts_with("spotify:"))
             return Response::createErrorResponse(ctx.getServerProtocolVersion(), Response::Error::Generic, "Invalid spotify playlist id");

        auto& session{ ctx.getDbSession() };
        auto transaction{ session.createReadTransaction() };

        db::Track::FindParameters params;
        std::string name;
        std::string description;

        if (*id == "spotify:release_radar")
        {
            name = "Release Radar";
            description = "Recent releases and new discoveries.";
            params.setSortMethod(db::TrackSortMethod::OriginalDateDescAndRelease);
            params.range = db::Range{ 0, 50 };
        }
        else if (*id == "spotify:sets")
        {
            name = "Sets & Mixes";
            description = "Long tracks (> 10 minutes)";
            params.minDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::Random);
            params.range = db::Range{ 0, 50 };
        }
        else if (id->starts_with("spotify:genre:"))
        {
            std::string genreName = id->substr(std::string("spotify:genre:").length());
            name = genreName;
            description = "Curated " + genreName + " tracks.";

            if (auto genreType = db::ClusterType::find(session, "genre"))
            {
                if (auto cluster = genreType->getCluster(genreName))
                {
                    params.filters.clusters.push_back(cluster->getId());
                }
            }
            params.setSortMethod(db::TrackSortMethod::Random);
            params.range = db::Range{ 0, 50 };
        }
        else
        {
             return Response::createErrorResponse(ctx.getServerProtocolVersion(), Response::Error::Generic, "Unknown spotify playlist id");
        }

        Response response{ Response::createOkResponse(ctx.getServerProtocolVersion()) };
        auto& playlistNode = response.createNode("playlist");
        playlistNode.setAttribute("id", *id);
        playlistNode.setAttribute("name", name);
        playlistNode.setAttribute("comment", description);
        playlistNode.setAttribute("owner", "LMS");
        playlistNode.setAttribute("public", true);

        db::Track::find(session, params, [&](const db::Track::pointer& track) {
            playlistNode.addArrayChild("entry", createSongNode(ctx, track, ctx.getUser()));
        });

        return response;
    }

    Response handleGetSpotifyTracks(RequestContext& ctx)
    {
        auto& session{ ctx.getDbSession() };
        auto transaction{ session.createReadTransaction() };

        db::Track::FindParameters params;

        if (auto genre = ctx.getQueryParameter("genre"))
        {
            if (auto genreType = db::ClusterType::find(session, "genre"))
            {
                if (auto cluster = genreType->getCluster(*genre))
                {
                    params.filters.clusters.push_back(cluster->getId());
                }
            }
        }

        if (auto sort = ctx.getQueryParameter("sort"))
        {
            if (*sort == "recent")
                params.setSortMethod(db::TrackSortMethod::OriginalDateDescAndRelease);
            else if (*sort == "added")
                params.setSortMethod(db::TrackSortMethod::AddedDateDesc);
            else if (*sort == "random")
                params.setSortMethod(db::TrackSortMethod::Random);
            else if (*sort == "alpha")
                params.setSortMethod(db::TrackSortMethod::Name);
        }

        if (auto minDuration = ctx.getQueryParameter("minDuration"))
        {
            try {
                params.minDuration = std::chrono::minutes(std::stoi(*minDuration));
            } catch (...) {}
        }

        int offset = ctx.getQueryParameterAsInt("offset", 0);
        int count = ctx.getQueryParameterAsInt("count", 50);
        params.range = db::Range{ static_cast<std::size_t>(offset), static_cast<std::size_t>(count) };

        Response response{ Response::createOkResponse(ctx.getServerProtocolVersion()) };
        auto& tracksNode = response.createArrayNode("tracks");

        db::Track::find(session, params, [&](const db::Track::pointer& track) {
            tracksNode.addChild(createSongNode(ctx, track, ctx.getUser()));
        });

        return response;
    }
} // namespace lms::api::subsonic
