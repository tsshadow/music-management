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

#include <algorithm>
#include <set>
#include <span>
#include <vector>

#include <Wt/Dbo/Exception.h>

#include "core/ILogger.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Cluster.hpp"

#include "ScanContext.hpp"
#include "ScanScope.hpp"

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

        // Recomputes the counts of `clusterIds` in one read transaction and returns those that
        // moved. Each cluster looked at adds one to `processedCount`.
        std::vector<ClusterStats> computeChangedStats(db::Session& dbSession, std::span<const db::ClusterId> clusterIds, const bool& abortScan, std::size_t& processedCount)
        {
            std::vector<ClusterStats> changedStats;
            auto transaction{ dbSession.createReadTransaction() };

            for (const db::ClusterId clusterId : clusterIds)
            {
                if (abortScan)
                    break;

                const db::Cluster::pointer cluster{ db::Cluster::find(dbSession, clusterId) };
                if (!cluster)
                    continue;

                const ClusterStats stats{ .clusterId = clusterId, .trackCount = db::Cluster::computeTrackCount(dbSession, clusterId), .releaseCount = db::Cluster::computeReleaseCount(dbSession, clusterId) };
                if (stats.trackCount != cluster->getTrackCount() || stats.releaseCount != cluster->getReleasesCount())
                    changedStats.push_back(stats);

                ++processedCount;
            }

            return changedStats;
        }

        // The clusters a scoped scan recomputes: those of its tracks, plus every cluster whose
        // cached track count went stale (bug report 141).
        std::vector<db::ClusterId> collectScopedClusterIds(db::Session& dbSession, const ScanScope& scope)
        {
            std::set<db::ClusterId> clusterIds{ std::cbegin(scope.clusters), std::cend(scope.clusters) };
            {
                auto transaction{ dbSession.createReadTransaction() };
                for (const db::ClusterId clusterId : db::Cluster::findIdsWithOutdatedTrackCount(dbSession))
                    clusterIds.insert(clusterId);
            }
            return std::vector<db::ClusterId>(std::cbegin(clusterIds), std::cend(clusterIds));
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

        // A batch the previous scan could not write may belong to any cluster: that retry covers
        // the whole library, as does a library-wide scan.
        const ScanScope* scope{ _retryPending ? nullptr : getScanScope(context) };
        _retryPending = false;
        std::size_t updatedCount{};

        // Counts are computed in a read transaction and only the clusters whose counts moved
        // are written, in one write transaction per batch. This step used to open a write
        // transaction per cluster and rewrite every one of them, changed or not -- thousands of
        // trips for the write lock on every scan that had a single change, each of them a chance
        // to meet music-manager holding it (bug report 132). Returns false to stop.
        auto processClusters = [&](std::span<const ClusterId> clusterIds) {
            const std::vector<ClusterStats> changedStats{ computeChangedStats(dbSession, clusterIds, _abortScan, context.currentStepStats.processedElems) };

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
        };

        constexpr std::size_t batchSize{ 100 };

        if (scope)
        {
            // A scoped scan (bug report 141): the clusters of its tracks, plus every cluster
            // whose cached track count no longer matches its rows -- the genre a retagged track
            // left, the one a removed track was in -- which the scope cannot name any more.
            const std::vector<ClusterId> clusterIds{ collectScopedClusterIds(dbSession, *scope) };

            context.currentStepStats.totalElems = clusterIds.size();
            for (std::size_t offset{}; offset < clusterIds.size(); offset += batchSize)
            {
                const std::span<const ClusterId> batch{ std::span{ clusterIds }.subspan(offset, std::min(batchSize, clusterIds.size() - offset)) };
                if (!processClusters(batch))
                    break;
            }
        }
        else
        {
            const std::size_t clusterCount{ [&] {
                auto transaction{ dbSession.createReadTransaction() };
                return Cluster::getCount(dbSession);
            }() };

            context.currentStepStats.totalElems = clusterCount;

            foreachSubRange(Range{ 0, clusterCount }, batchSize, [&](Range range) {
                std::vector<ClusterId> clusterIds;
                {
                    auto transaction{ dbSession.createReadTransaction() };

                    Cluster::FindParameters params;
                    params.setRange(range);
                    clusterIds = Cluster::findIds(dbSession, params).results;
                }

                return processClusters(clusterIds);
            });
        }

        LMS_LOG(DBUPDATER, DEBUG, "Recomputed stats for " << context.currentStepStats.processedElems << " clusters, " << updatedCount << " updated!");
    }
} // namespace lms::scanner
