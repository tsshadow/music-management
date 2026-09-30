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

#include <chrono>
#include <deque>
#include <filesystem>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "PriorityFolderQueue.hpp"
#include "ScanContext.hpp"
#include "ScanStepSequence.hpp"
#include "steps/BatchedRemoval.hpp"
#include "steps/IScanStep.hpp"

// Bug report 136. Names here are deliberately distinct from the helpers in ScanStepSequence.cpp:
// the release image builds with CMAKE_UNITY_BUILD, which merges the anonymous namespaces of the
// test files into one translation unit.
namespace lms::scanner::tests
{
    namespace
    {
        using RemovalClock = PriorityFolderQueue::Clock;

        // What a removed row costs on production: an image row cascades to artwork and on to
        // four unindexed preferred_artwork_id columns.
        constexpr std::chrono::milliseconds removalCostPerRow{ 200 };
        constexpr std::size_t removalWriteBatchSize{ 50 };

        constexpr PriorityFolderQueue::Timing removalQueueTiming{
            .collect = ScanRequestCollector::Timing{ .quietPeriod = std::chrono::seconds{ 5 }, .maxDelay = std::chrono::seconds{ 60 } },
            .minGapDuringLibraryScan = std::chrono::seconds{ 120 },
        };

        // The scoped scan a priority pass runs: notes the folders and the moment it ran.
        class RecordingPassStep : public IScanStep
        {
        public:
            RecordingPassStep(const RemovalClock::time_point& now, std::vector<RemovalClock::time_point>& ranAt, std::vector<std::filesystem::path>& folders)
                : _now{ now }
                , _ranAt{ ranAt }
                , _folders{ folders }
            {
            }

            ScanStep getStep() const override { return ScanStep::ScanFiles; }
            core::LiteralString getStepName() const override { return "recording pass"; }
            bool needProcess(const ScanContext&) const override { return true; }

            void process(ScanContext& context) override
            {
                _ranAt.push_back(_now);
                _folders.insert(std::end(_folders), std::cbegin(context.scanOptions.scanDirectories), std::cend(context.scanOptions.scanDirectories));
            }

        private:
            const RemovalClock::time_point& _now;
            std::vector<RemovalClock::time_point>& _ranAt;
            std::vector<std::filesystem::path>& _folders;
        };

        // A deque of ids 0 .. count-1, as ScanStepCheckForRemovedFiles collects them.
        std::deque<int> makePendingRemovals(int count)
        {
            std::deque<int> ids;
            for (int id{}; id < count; ++id)
                ids.push_back(id);
            return ids;
        }
    } // namespace

    // The production case: a library scan finds 20,000 rows to remove (about 67 minutes at
    // 0.2 s each) while the downloader announces a folder. The folder used to wait for the whole
    // removal; now it is read at the first write-batch boundary after it is due, and the removal
    // still removes every row exactly once.
    TEST(BatchedRemoval, aFolderAnnouncedDuringALongRemovalIsReadWithinOneWriteBatch)
    {
        PriorityFolderQueue queue{ removalQueueTiming };
        RemovalClock::time_point now{};
        bool interrupted{};

        std::vector<RemovalClock::time_point> passRanAt;
        std::vector<std::filesystem::path> passFolders;
        std::vector<std::unique_ptr<IScanStep>> passSteps;
        passSteps.push_back(std::make_unique<RecordingPassStep>(now, passRanAt, passFolders));

        // The previous pass has just ended: the two-minute gap starts now.
        queue.priorityPassFinished(now);
        const RemovalClock::time_point announcedAt{ now + std::chrono::seconds{ 1 } };

        std::deque<int> pending{ makePendingRemovals(20'000) };
        std::vector<int> removed;
        bool announced{};

        const std::size_t removedCount{ removeInWriteBatches(
            pending, removalWriteBatchSize, false,
            [&](std::span<const int> ids) {
                removed.insert(std::end(removed), std::cbegin(ids), std::cend(ids));
                now += removalCostPerRow * static_cast<long>(ids.size());
            },
            [&] {
                if (!announced && now >= announcedAt)
                {
                    queue.add({ "/music/Soundcloud/2TD" }, announcedAt);
                    announced = true;
                }
                if (queue.isDue(now, PriorityFolderQueue::Moment::DuringLibraryScan))
                {
                    if (runPriorityPass(passSteps, queue, now, interrupted))
                        queue.priorityPassFinished(now);
                }
            }) };

        EXPECT_EQ(removedCount, 20'000);
        ASSERT_EQ(removed.size(), 20'000);
        for (int id{}; id < 20'000; ++id)
            ASSERT_EQ(removed[static_cast<std::size_t>(id)], id); // each once, in order
        EXPECT_TRUE(pending.empty());

        // Due at the end of the gap (t=120 s); one write batch is 10 s of removal.
        ASSERT_EQ(passRanAt.size(), 1);
        EXPECT_EQ(passFolders, std::vector<std::filesystem::path>{ "/music/Soundcloud/2TD" });
        EXPECT_LE(passRanAt.front() - RemovalClock::time_point{}, std::chrono::seconds{ 120 } + removalCostPerRow * static_cast<long>(removalWriteBatchSize));
        EXPECT_LT(passRanAt.front(), now - std::chrono::minutes{ 60 }); // long before the removal ended
    }

    // Finishing the job queue for a pass hands in the ids the last checks found; the same call
    // removes them.
    TEST(BatchedRemoval, idsAddedBetweenBatchesAreRemovedInTheSameCall)
    {
        std::deque<int> pending{ makePendingRemovals(60) };
        std::vector<int> removed;
        std::size_t batches{};

        const std::size_t removedCount{ removeInWriteBatches(
            pending, removalWriteBatchSize, false,
            [&](std::span<const int> ids) {
                removed.insert(std::end(removed), std::cbegin(ids), std::cend(ids));
                ++batches;
            },
            [&] {
                if (batches == 1)
                    pending.push_back(1000);
            }) };

        EXPECT_EQ(removedCount, 61);
        EXPECT_EQ(batches, 2);
        EXPECT_EQ(removed.back(), 1000);
        EXPECT_TRUE(pending.empty());
    }

    // In the middle of the walk only full batches go: a short remainder waits for more ids or
    // for the end of the step.
    TEST(BatchedRemoval, fullBatchesOnlyLeavesTheRemainder)
    {
        std::deque<int> pending{ makePendingRemovals(120) };
        std::size_t afterBatchCalls{};

        const std::size_t removedCount{ removeInWriteBatches(pending, removalWriteBatchSize, true, [](std::span<const int>) {}, [&] { ++afterBatchCalls; }) };

        EXPECT_EQ(removedCount, 100);
        EXPECT_EQ(afterBatchCalls, 2);
        EXPECT_EQ(pending.size(), 20);
        EXPECT_EQ(pending.front(), 100);

        EXPECT_EQ(removeInWriteBatches(pending, removalWriteBatchSize, false, [](std::span<const int>) {}, [] {}), 20);
        EXPECT_TRUE(pending.empty());
    }

    TEST(BatchedRemoval, nothingPendingMeansNoWriteTransaction)
    {
        std::deque<int> pending;
        std::size_t transactions{};

        EXPECT_EQ(removeInWriteBatches(pending, removalWriteBatchSize, false, [&](std::span<const int>) { ++transactions; }, [] {}), 0);
        EXPECT_EQ(transactions, 0);
    }
} // namespace lms::scanner::tests
