/*
 * Copyright (C) 2026 Teun Schriks
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

#include "ScanScope.hpp"

#include <set>

#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/PlayListFile.hpp"
#include "database/objects/Track.hpp"

namespace lms::scanner
{
    namespace
    {
        template<typename IdType>
        std::vector<IdType> toVector(const std::set<IdType>& ids)
        {
            return std::vector<IdType>(std::cbegin(ids), std::cend(ids));
        }

        // Calls `func` for every id under `directory`, in pages, through one of the
        // findAbsoluteFilePathInDirectory functions the removal check uses as well.
        template<typename Object, typename IdType, typename Func>
        void forEachIdInDirectory(db::Session& session, const std::filesystem::path& directory, const Func& func)
        {
            constexpr std::size_t pageSize{ 1000 };

            IdType lastRetrievedId{};
            while (true)
            {
                const IdType previousId{ lastRetrievedId };
                bool keepGoing{ true };
                Object::findAbsoluteFilePathInDirectory(session, lastRetrievedId, pageSize, directory, [&](IdType id, const std::filesystem::path&) {
                    if (keepGoing)
                        keepGoing = func(id);
                });

                if (!keepGoing || lastRetrievedId == previousId)
                    break;
            }
        }
    } // namespace

    std::optional<ScanScope> computeScanScope(db::Session& session, std::span<const std::filesystem::path> directories, std::size_t maxTrackCount)
    {
        auto transaction{ session.createReadTransaction() };

        // 1. The tracks the scan can have touched: everything under the folders.
        std::set<db::TrackId> tracksInDirectories;
        for (const std::filesystem::path& directory : directories)
        {
            forEachIdInDirectory<db::Track, db::TrackId>(session, directory, [&](db::TrackId trackId) {
                tracksInDirectories.insert(trackId);
                return tracksInDirectories.size() <= maxTrackCount;
            });

            if (tracksInDirectories.size() > maxTrackCount)
                return std::nullopt;
        }

        // 2. Their releases, and every other track of those releases.
        std::set<db::ReleaseId> releases;
        for (const db::TrackId trackId : tracksInDirectories)
        {
            if (const db::Track::pointer track{ db::Track::find(session, trackId) }; track && track->getReleaseId().isValid())
                releases.insert(track->getReleaseId());
        }

        std::set<db::TrackId> tracks{ tracksInDirectories };
        for (const db::ReleaseId releaseId : releases)
        {
            for (const db::TrackId trackId : db::Track::findIds(session, db::Track::FindParameters{}.setRelease(releaseId)).results)
                tracks.insert(trackId);

            if (tracks.size() > maxTrackCount)
                return std::nullopt;
        }

        // 3. What hangs off those tracks.
        std::set<db::MediumId> mediums;
        std::set<db::ArtistId> artists;
        std::set<db::ClusterId> clusters;
        for (const db::TrackId trackId : tracks)
        {
            if (const db::Track::pointer track{ db::Track::find(session, trackId) }; track && track->getMediumId().isValid())
                mediums.insert(track->getMediumId());

            for (const db::ArtistId artistId : db::Artist::findIds(session, db::Artist::FindParameters{}.setTrack(trackId)).results)
                artists.insert(artistId);

            for (const db::ClusterId clusterId : db::Cluster::findIds(session, db::Cluster::FindParameters{}.setTrack(trackId)).results)
                clusters.insert(clusterId);
        }

        // 4. Playlists are matched by their own location only.
        std::set<db::PlayListFileId> playListFiles;
        for (const std::filesystem::path& directory : directories)
        {
            forEachIdInDirectory<db::PlayListFile, db::PlayListFileId>(session, directory, [&](db::PlayListFileId playListFileId) {
                playListFiles.insert(playListFileId);
                return true;
            });
        }

        return ScanScope{
            .tracks = toVector(tracks),
            .releases = toVector(releases),
            .mediums = toVector(mediums),
            .artists = toVector(artists),
            .clusters = toVector(clusters),
            .playListFiles = toVector(playListFiles),
        };
    }
} // namespace lms::scanner
