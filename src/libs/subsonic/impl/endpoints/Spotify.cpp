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
#include "database/objects/User.hpp"
#include "responses/Playlist.hpp"
#include "responses/Song.hpp"
#include "core/Service.hpp"
#include "services/scrobbling/IScrobblingService.hpp"

#include <unordered_map>

namespace lms::api::subsonic
{
    namespace
    {
        std::string normalizeArtist(std::string_view artist)
        {
            std::string lower{ core::stringUtils::stringToLower(artist) };
            
            // Basic splitting by common separators
            std::vector<std::string_view> separators = { ",", "&", " feat.", " ft.", " and " };
            std::vector<std::string_view> parts_view = core::stringUtils::splitString(lower, std::span{ separators });
            
            std::vector<std::string> parts;
            for (auto p : parts_view)
            {
                auto trimmed = core::stringUtils::stringTrim(p);
                if (!trimmed.empty())
                    parts.push_back(std::string(trimmed));
            }
            
            std::sort(parts.begin(), parts.end());
            
            return core::stringUtils::joinStrings(parts, "|");
        }

        std::string normalizeTitle(std::string_view title)
        {
            std::string lower{ core::stringUtils::stringToLower(title) };
            std::string normalized{ core::stringUtils::stringTrim(lower) };
            
            // Strip version info from key to treat them as duplicates
            auto strip = [&](std::string_view search) {
                auto pos = normalized.find(search);
                if (pos != std::string::npos)
                    normalized.erase(pos, search.length());
            };
            
            strip("(radio edit)");
            strip("radio edit");
            strip("(extended mix)");
            strip("extended mix");
            strip("(original mix)");
            strip("original mix");
            strip("(edit)");
            strip("edit");
            strip("(official videoclip)");
            strip("official videoclip");
            strip("(official video clip)");
            strip("official video clip");
            strip("(official video)");
            strip("official video");
            strip("(official hardstyle visualizer)");
            strip("official hardstyle visualizer");
            strip("(hardstyle videoclip)");
            strip("hardstyle videoclip");
            
            return std::string(core::stringUtils::stringTrim(normalized));
        }

        int getTrackScore(const db::Track::pointer& track)
        {
            int score = 0;
            
            // Quality
            std::string suffix = core::stringUtils::stringToLower(track->getAbsoluteFilePath().extension().string());
            if (!suffix.empty() && suffix[0] == '.')
                suffix = suffix.substr(1);

            int bitRate = static_cast<int>(track->getBitrate() / 1000);
            
            if (suffix == "flac") score += 10000;
            else if (suffix == "mp3")
            {
                if (bitRate >= 320) score += 5000;
                else if (bitRate >= 192) score += 2000;
                else if (bitRate > 0) score += 1000;
            }
            
            // Version
            std::string name = core::stringUtils::stringToLower(track->getName());
            bool isVideo = name.find("videoclip") != std::string::npos || 
                           name.find("official video") != std::string::npos ||
                           name.find("video clip") != std::string::npos;
            bool isVisualizer = name.find("visualizer") != std::string::npos;

            if (name.find("radio edit") != std::string::npos) score += 500;
            else if (name.find("extended mix") != std::string::npos) score += 100;
            else if (name.find("original mix") != std::string::npos) score += 300;
            else score += 200;
            
            if (isVideo) score -= 50;
            else if (isVisualizer) score -= 40;

            return score;
        }

        std::string getDedupeKey(const db::Track::pointer& track)
        {
            return normalizeArtist(track->getArtistDisplayName()) + ":::" + normalizeTitle(track->getName());
        }

        void findTracks(db::Session& session, db::Track::FindParameters& params, const std::map<std::string, std::set<db::ClusterId>>& clusterGroups, bool deduplicate, int& nextOffset, bool& moreResults, std::function<void(const db::Track::pointer&)> callback)
        {
            int initialOffset = params.range ? static_cast<int>(params.range->offset) : 0;
            int requestedCount = params.range ? static_cast<int>(params.range->size) : 50;

            if (deduplicate)
            {
                std::unordered_map<std::string, db::Track::pointer> bestTracks;
                std::vector<std::string> orderedKeys;
                
                int uniqueCount = 0;
                int totalScanned = 0;
                bool batchMoreResults = false;
                
                // We iterate in batches to fill requestedCount unique tracks
                int currentScanOffset = initialOffset;
                int scanBatchSize = std::max(requestedCount, 100);
                const int maxScanCount = 5000; // Limit scanning to avoid server hangs
                
                while (uniqueCount < requestedCount && totalScanned < maxScanCount)
                {
                    params.range = db::Range{ static_cast<std::size_t>(currentScanOffset), static_cast<std::size_t>(scanBatchSize) };
                    
                    int batchScanned = 0;
                    db::Track::find_advanced(session, params, clusterGroups, [&](const db::Track::pointer& track) {
                        batchScanned++;
                        if (uniqueCount >= requestedCount)
                            return;

                        std::string key = getDedupeKey(track);
                        auto it = bestTracks.find(key);
                        if (it == bestTracks.end())
                        {
                            bestTracks[key] = track;
                            orderedKeys.push_back(key);
                            uniqueCount++;
                        }
                        else
                        {
                            if (getTrackScore(track) > getTrackScore(it->second))
                            {
                                bestTracks[key] = track;
                            }
                        }
                    });
                    
                    totalScanned += batchScanned;
                    currentScanOffset += batchScanned;
                    
                    // We need to know if there were more results in the batch
                    // find_advanced doesn't easily tell us this for raw SQL unless we check if we got scanBatchSize results
                    batchMoreResults = (batchScanned >= scanBatchSize);

                    if (!batchMoreResults || uniqueCount >= requestedCount)
                        break;
                }

                for (const auto& key : orderedKeys)
                {
                    callback(bestTracks[key]);
                }
                
                moreResults = batchMoreResults;
                nextOffset = initialOffset + totalScanned;
            }
            else
            {
                int actualCount = 0;
                db::Track::find_advanced(session, params, clusterGroups, [&](const db::Track::pointer& track) {
                    actualCount++;
                    callback(track);
                });
                nextOffset = initialOffset + actualCount;
                
                // Simplified moreResults check
                moreResults = (actualCount >= requestedCount);
            }
        }
    }
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
        int offset = getParameterAs<int>(ctx.getParameters(), "offset").value_or(0);
        int count = getParameterAs<int>(ctx.getParameters(), "count").value_or(50);
        params.range = db::Range{ static_cast<std::size_t>(offset), static_cast<std::size_t>(count) };

        if (auto seed = getParameterAs<int>(ctx.getParameters(), "seed"))
        {
            params.randomSeed = *seed;
        }

        std::string name;
        std::string description;

        if (id == "spotify:release_radar")
        {
            name = "Release Radar";
            description = "Recent releases and new discoveries.";
            params.maxDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::OriginalDateDescAndRelease);
        }
        else if (id == "spotify:sets")
        {
            name = "Sets & Mixes";
            description = "Sets and mixes";
            params.minDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::Random);
        }
        else if (id == "spotify:songs")
        {
            name = "Songs";
            description = "All songs";
            params.maxDuration = std::chrono::minutes(10);
            params.setSortMethod(db::TrackSortMethod::Random);
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

        bool moreResults = false;
        int nextOffset = 0;
        findTracks(session, params, {}, true /* always deduplicate curated */, nextOffset, moreResults, [&](const db::Track::pointer& track) {
            playlistNode.addArrayChild("entry", createSongNode(ctx, track, true));
        });

        playlistNode.setAttribute("moreResults", moreResults);
        playlistNode.setAttribute("nextOffset", nextOffset);

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

        std::map<std::string, std::set<db::ClusterId>> clusterGroups;
        if (auto genre = getParameterAs<std::string>(ctx.getParameters(), "genre"))
        {
            if (auto genreType = db::ClusterType::find(session, "GENRE"))
            {
                if (auto cluster = genreType->getCluster(*genre))
                {
                    clusterGroups["GENRE"].insert(cluster->getId());
                }
            }
        }

        if (auto year = getParameterAs<std::string>(ctx.getParameters(), "year"))
        {
            if (auto yearType = db::ClusterType::find(session, "YEAR"))
            {
                if (auto cluster = yearType->getCluster(*year))
                {
                    clusterGroups["YEAR"].insert(cluster->getId());
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

        if (auto seed = getParameterAs<int>(ctx.getParameters(), "seed"))
        {
            params.randomSeed = *seed;
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

        params.includeUnrated = true;
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

        bool deduplicate = getParameterAs<bool>(ctx.getParameters(), "deduplicate").value_or(false);
        bool moreResults = false;
        int nextOffset = 0;

        findTracks(session, params, clusterGroups, deduplicate, nextOffset, moreResults, [&](const db::Track::pointer& track) {
            tracksNode.addArrayChild("track", createSongNode(ctx, track, true));
        });

        tracksNode.setAttribute("moreResults", moreResults);
        tracksNode.setAttribute("nextOffset", nextOffset);

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

        auto results = db::Listen::find(session, params);
        for (db::ListenId listenId : results.results)
        {
            if (auto listen = db::Listen::find(session, listenId))
            {
                if (auto track = listen->getTrack())
                {
                    auto entryNode{ createSongNode(ctx, track, true) };
                    entryNode.setAttribute("listenedAt", listen->getDateTime().toString().toUTF8());
                    historyNode.addArrayChild("entry", std::move(entryNode));
                }
            }
        }

        historyNode.setAttribute("moreResults", results.moreResults);

        return response;
    }

    Response handleSpotifyImportFromListenBrainz(RequestContext& ctx)
    {
        core::Service<scrobbling::IScrobblingService>::get()->synchronize(ctx.getUser()->getId());
        return Response::createOkResponse(ctx.getServerProtocolVersion());
    }
} // namespace lms::api::subsonic
