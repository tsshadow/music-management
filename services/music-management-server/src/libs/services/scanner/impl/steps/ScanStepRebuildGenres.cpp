/*
 * Copyright (C) 2026 Emeric Poupon
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

#include "ScanStepRebuildGenres.hpp"

#include <algorithm>

#include "core/ILogger.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/Track.hpp"

#include "audio/IAudioFileInfo.hpp"
#include "audio/IAudioFileInfoParser.hpp"

#include "ScanContext.hpp"
#include "ScannerSettings.hpp"
#include "scanners/audiofile/AudioFileInfoParserSet.hpp"
#include "scanners/audiofile/TrackMetadataParser.hpp"

namespace lms::scanner
{
    bool ScanStepRebuildGenres::needProcess(const ScanContext& context) const
    {
        return context.scanOptions.rebuildGenres;
    }

    void ScanStepRebuildGenres::process(ScanContext& context)
    {
        db::Session& session{ _db.getTLSSession() };

        db::ClusterType::pointer genreType;
        {
            auto transaction{ session.createReadTransaction() };
            genreType = db::ClusterType::find(session, "GENRE");
            context.currentStepStats.totalElems = db::Track::getCount(session);
        }

        if (!genreType)
        {
            LMS_LOG(DBUPDATER, INFO, "GENRE cluster type not found, nothing to rebuild");
            return;
        }

        {
            auto transaction{ session.createWriteTransaction() };
            auto clusters = genreType->getClusters();
            std::size_t clusterCount = clusters.size();
            for (auto& cluster : clusters)
            {
                cluster.remove();
            }
            LMS_LOG(DBUPDATER, INFO, "Removed " << clusterCount << " GENRE clusters");
        }

        AudioFileInfoParserSet parserSet{ createAudioFileInfoParserSet() };
        TrackMetadataParser metadataParser{ { .defaultTagDelimiters = _settings.defaultTagDelimiters } };

        constexpr std::size_t batchSize = 100;
        db::RangeResults<db::TrackId> trackIds;
        std::size_t rebuildCount = 0;

        while (!_abortScan)
        {
            {
                auto transaction{ session.createReadTransaction() };
                trackIds = db::Track::findIds(session, db::Track::FindParameters{}.setRange(db::Range{ context.currentStepStats.processedElems, batchSize }));
            }

            if (trackIds.results.empty())
                break;

            for (const db::TrackId trackId : trackIds.results)
            {
                if (_abortScan)
                    break;

                auto transaction{ session.createWriteTransaction() };
                db::Track::pointer track = db::Track::find(session, trackId);
                if (!track)
                    continue;

                const std::filesystem::path path = track->getAbsoluteFilePath();
                try
                {
                    audio::AudioFileInfoParseOptions options;
                    options.audioPropertiesReadStyle = audio::AudioFileInfoParseOptions::AudioPropertiesReadStyle::Fast;
                    options.readImages = false;

                    if (const std::unique_ptr<audio::IAudioFileInfo> fileInfo{ parserSet.taglibParser->parse(path, options) })
                    {
                        const audio::ITagReader* tagReader{ fileInfo->getTagReader() };
                        if (!tagReader)
                            continue;

                        const Track metadata = metadataParser.parseTrackMetaData(*tagReader);

                        if (!metadata.genres.empty())
                        {
                            std::vector<db::Cluster::pointer> clusters = track->getClusters();
                            // GENRE clusters are already removed from the DB, so they should not be in 'clusters'
                            // but we filter them just in case some caching is involved
                            clusters.erase(std::remove_if(clusters.begin(), clusters.end(), [&](const db::Cluster::pointer& c) {
                                               return c->getType()->getName() == "GENRE";
                                           }),
                                           clusters.end());

                            for (const std::string& genreName : metadata.genres)
                            {
                                db::Cluster::pointer cluster = genreType->getCluster(genreName);
                                if (!cluster)
                                    cluster = session.create<db::Cluster>(genreType, genreName);

                                clusters.push_back(cluster);
                            }
                            track.modify()->setClusters(clusters);
                            rebuildCount++;
                        }
                    }
                }
                catch (const std::exception& e)
                {
                    LMS_LOG(DBUPDATER, WARNING, "Failed to rebuild genres for " << path << ": " << e.what());
                }
            }

            context.currentStepStats.processedElems += trackIds.results.size();
            _progressCallback(context.currentStepStats);
        }

        LMS_LOG(DBUPDATER, INFO, "Rebuilt genres for " << rebuildCount << " tracks");
    }
} // namespace lms::scanner
