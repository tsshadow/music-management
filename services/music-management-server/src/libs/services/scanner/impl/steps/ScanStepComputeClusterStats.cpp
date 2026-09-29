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

#include "ScanStepComputeClusterStats.hpp"

#include <vector>

#include <Wt/Dbo/Exception.h>

#include "core/ILogger.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Cluster.hpp"

#include "ScanContext.hpp"

namespace lms::scanner
{
    namespace
    {
        struct ClusterStats
        {
            db::ClusterId clusterId;
            std::size_t trackCount{};
            std::size_t releaseCount{};
        };

        void logWriteFailure(std::size_t clusterCount, const Wt::Dbo::Exception& e)
        {
            LMS_LOG(DBUPDATER, WARNING, "Could not write the stats of " << clusterCount << " clusters, retrying on the next scan: " << e.what());
        }

        // Writes one batch of counts in one write transaction. Returns false, and leaves the
        // session clean, when the database refused it -- typically still locked by
        // music-manager after busy_timeout. It must not throw: this runs on the scanner
        // thread, Wt::WIOService has no catch, and an exception there ends the process in
        // std::terminate, which is what "update cluster ... database is locked" did twice in
        // three days (bug report 132).
        bool writeStats(db::Session& dbSession, const std::vector<ClusterStats>& changedStats)
        {
            bool written{};
            try
            {
                // Throws from here when BEGIN IMMEDIATE times out; nothing was touched yet.
                auto transaction{ dbSession.createWriteTransaction() };

                // The try sits inside the transaction so that the session is cleaned up
                // before WriteTransaction's destructor commits: it commits even while an
                // exception unwinds, and it would flush the failed updates a second time.
                try
                {
                    for (const ClusterStats& stats : changedStats)
                    {
                        db::Cluster::pointer cluster{ db::Cluster::find(dbSession, stats.clusterId) };
                        if (!cluster)
                            continue;

                        cluster.modify()->setTrackCount(stats.trackCount);
                        cluster.modify()->setReleaseCount(stats.releaseCount);
                    }

                    // Flushed here, inside the try, rather than by the commit in
                    // WriteTransaction's destructor, which is outside every catch.
                    dbSession.getDboSession()->flush();
                    written = true;
                }
                catch (const Wt::Dbo::Exception& e)
                {
                    // A failed flush leaves the modified clusters dirty in this thread's
                    // session (Wt's rollback does not reread them), and every later write
                    // transaction on this thread would flush them again. Drop them.
                    dbSession.getDboSession()->discardUnflushed();
                    logWriteFailure(changedStats.size(), e);
                }
            } // commits here
            catch (const Wt::Dbo::Exception& e)
            {
                dbSession.getDboSession()->discardUnflushed();
                logWriteFailure(changedStats.size(), e);
                written = false;
            }

            return written;
        }
    } // namespace

    bool ScanStepComputeClusterStats::needProcess(const ScanContext& context) const
    {
        if (context.stats.getChangesCount() > 0 || _retryPending)
            return true;

        // Changes alone are not enough to keep the cached counts correct: this is the
        // second to last step, so a scan that is aborted (or that crashes) after the
        // clusters were created leaves every count at zero, and every later scan without
        // changes would skip this step and keep it that way forever -- which is exactly
        // how getGenres ends up answering songCount="0" for the whole library.
        db::Session& dbSession{ _db.getTLSSession() };
        auto transaction{ dbSession.createReadTransaction() };
        return db::Cluster::hasOutdatedStats(dbSession);
    }

    void ScanStepComputeClusterStats::process(ScanContext& context)
    {
        using namespace db;

        Session& dbSession{ _db.getTLSSession() };

        const std::size_t clusterCount{ [&] {
            auto transaction{ dbSession.createReadTransaction() };
            return Cluster::getCount(dbSession);
        }() };

        context.currentStepStats.totalElems = clusterCount;
        _retryPending = false;
        std::size_t updatedCount{};

        foreachSubRange(Range{ 0, clusterCount }, 100, [&](Range range) {
            // Counts are computed in a read transaction and only the clusters whose counts
            // moved are written, in one write transaction per batch. This step used to open a
            // write transaction per cluster and rewrite every one of them, changed or not --
            // thousands of trips for the write lock on every scan that had a single change,
            // each of them a chance to meet music-manager holding it (bug report 132).
            std::vector<ClusterStats> changedStats;
            {
                auto transaction{ dbSession.createReadTransaction() };

                Cluster::FindParameters params;
                params.setRange(range);
                const std::vector<ClusterId> clusterIds{ Cluster::findIds(dbSession, params).results };

                for (const ClusterId clusterId : clusterIds)
                {
                    if (_abortScan)
                        break;

                    const Cluster::pointer cluster{ Cluster::find(dbSession, clusterId) };
                    if (!cluster)
                        continue;

                    const ClusterStats stats{ .clusterId = clusterId, .trackCount = Cluster::computeTrackCount(dbSession, clusterId), .releaseCount = Cluster::computeReleaseCount(dbSession, clusterId) };
                    if (stats.trackCount != cluster->getTrackCount() || stats.releaseCount != cluster->getReleasesCount())
                        changedStats.push_back(stats);

                    context.currentStepStats.processedElems++;
                }
            }

            if (!changedStats.empty() && !_abortScan)
            {
                if (!writeStats(dbSession, changedStats))
                {
                    _retryPending = true;
                    return false;
                }
                updatedCount += changedStats.size();
            }

            _progressCallback(context.currentStepStats);

            return !_abortScan;
        });

        LMS_LOG(DBUPDATER, DEBUG, "Recomputed stats for " << context.currentStepStats.processedElems << " clusters, " << updatedCount << " updated!");
    }
} // namespace lms::scanner
