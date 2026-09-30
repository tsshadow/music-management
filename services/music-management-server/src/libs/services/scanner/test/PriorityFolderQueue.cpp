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

#include <atomic>
#include <string>
#include <thread>

#include <gtest/gtest.h>

#include "PriorityFolderQueue.hpp"

namespace lms::scanner::tests
{
    namespace
    {
        using Clock = PriorityFolderQueue::Clock;
        using Moment = PriorityFolderQueue::Moment;
        using std::chrono::seconds;

        constexpr PriorityFolderQueue::Timing timing{
            .collect = ScanRequestCollector::Timing{ .quietPeriod = seconds{ 5 }, .maxDelay = seconds{ 60 } },
            .minGapDuringLibraryScan = seconds{ 120 },
        };
    } // namespace

    TEST(PriorityFolderQueue, isEmptyUntilSomethingArrives)
    {
        PriorityFolderQueue queue{ timing };

        EXPECT_EQ(queue.pendingCount(), 0);
        EXPECT_FALSE(queue.deadline().has_value());
        EXPECT_FALSE(queue.isDue(Clock::time_point{} + seconds{ 3600 }, Moment::DuringLibraryScan));
        EXPECT_TRUE(queue.takeDue(Clock::time_point{} + seconds{ 3600 }, Moment::Idle).empty());
    }

    // The debounce that already applied to idle scoped scans applies inside a library scan too:
    // a folder is not read while the tagger is still writing to it.
    TEST(PriorityFolderQueue, aFolderBecomesDueAfterTheQuietPeriodAtEitherMoment)
    {
        PriorityFolderQueue queue{ timing };
        const Clock::time_point start{};

        queue.add({ "/music/Soundcloud/2TD" }, start);

        EXPECT_FALSE(queue.isDue(start + seconds{ 4 }, Moment::Idle));
        EXPECT_FALSE(queue.isDue(start + seconds{ 4 }, Moment::DuringLibraryScan));
        EXPECT_TRUE(queue.isDue(start + seconds{ 5 }, Moment::Idle));
        EXPECT_TRUE(queue.isDue(start + seconds{ 5 }, Moment::DuringLibraryScan));
    }

    TEST(PriorityFolderQueue, aFolderAnnouncedTwiceIsReadOnce)
    {
        PriorityFolderQueue queue{ timing };
        const Clock::time_point start{};

        queue.add({ "/music/Soundcloud/2TD", "/music/Youtube/Gearbox Digital" }, start);
        queue.add({ "/music/Soundcloud/2TD" }, start + seconds{ 1 });
        EXPECT_EQ(queue.pendingCount(), 2);

        const std::vector<std::filesystem::path> taken{ queue.takeDue(start + seconds{ 10 }, Moment::DuringLibraryScan) };
        EXPECT_EQ(taken.size(), 2);
        EXPECT_EQ(queue.pendingCount(), 0);
    }

    // A tagger round notifies a folder every few seconds for an hour. Without a gap, every step
    // boundary of the library scan would open a new priority pass and the library scan -- the
    // thing bug report 120 fought to let finish -- would crawl.
    TEST(PriorityFolderQueue, insideALibraryScanTheNextPassWaitsForTheGap)
    {
        PriorityFolderQueue queue{ timing };
        const Clock::time_point start{};

        queue.add({ "/music/A" }, start);
        ASSERT_EQ(queue.takeDue(start + seconds{ 5 }, Moment::DuringLibraryScan).size(), 1);
        queue.priorityPassFinished(start + seconds{ 65 });

        queue.add({ "/music/B" }, start + seconds{ 70 });

        EXPECT_FALSE(queue.isDue(start + seconds{ 100 }, Moment::DuringLibraryScan));
        EXPECT_TRUE(queue.takeDue(start + seconds{ 100 }, Moment::DuringLibraryScan).empty());
        EXPECT_EQ(queue.pendingCount(), 1); // still there, not dropped

        EXPECT_TRUE(queue.isDue(start + seconds{ 185 }, Moment::DuringLibraryScan));
        EXPECT_EQ(queue.takeDue(start + seconds{ 185 }, Moment::DuringLibraryScan).size(), 1);
    }

    // Once the library scan is over the gap no longer applies: nothing competes for the scanner.
    TEST(PriorityFolderQueue, theGapDoesNotHoldBackAnIdleScanner)
    {
        PriorityFolderQueue queue{ timing };
        const Clock::time_point start{};

        queue.priorityPassFinished(start);
        queue.add({ "/music/B" }, start + seconds{ 1 });

        EXPECT_TRUE(queue.isDue(start + seconds{ 6 }, Moment::Idle));
        EXPECT_FALSE(queue.isDue(start + seconds{ 6 }, Moment::DuringLibraryScan));
    }

    TEST(PriorityFolderQueue, takeHandsOutEverythingDueOrNot)
    {
        PriorityFolderQueue queue{ timing };

        queue.add({ "/music/A" }, Clock::time_point{});

        EXPECT_EQ(queue.take().size(), 1);
        EXPECT_EQ(queue.pendingCount(), 0);
        EXPECT_FALSE(queue.deadline().has_value());
    }

    // The web threads add while the scanner thread takes: nothing may be lost or duplicated.
    TEST(PriorityFolderQueue, concurrentAddsAndTakesLoseNothing)
    {
        PriorityFolderQueue queue{ timing };
        constexpr std::size_t folderCount{ 2'000 };
        const Clock::time_point farFuture{ Clock::time_point{} + std::chrono::hours{ 1 } };

        std::atomic<bool> addingDone{};
        std::thread adder{ [&] {
            for (std::size_t i{}; i < folderCount; ++i)
                queue.add({ std::filesystem::path{ "/music/folder" } / std::to_string(i) }, Clock::time_point{});
            addingDone = true;
        } };

        std::size_t takenCount{};
        while (!addingDone)
            takenCount += queue.takeDue(farFuture, Moment::Idle).size();
        adder.join();
        takenCount += queue.take().size();

        EXPECT_EQ(takenCount, folderCount);
    }
    // Bug report 136: one pass takes a bounded number of folders; the rest wait for the next pass,
    // and are due as soon as the gap after this one has passed.
    TEST(PriorityFolderQueue, aBoundedTakeLeavesTheRestForTheNextPass)
    {
        PriorityFolderQueue queue{ timing };
        const Clock::time_point start{};

        queue.add({ "/music/A", "/music/B", "/music/C" }, start);

        EXPECT_EQ(queue.takeDue(start + seconds{ 10 }, Moment::DuringLibraryScan, 2).size(), 2);
        queue.priorityPassFinished(start + seconds{ 40 });
        EXPECT_EQ(queue.pendingCount(), 1);

        EXPECT_FALSE(queue.isDue(start + seconds{ 100 }, Moment::DuringLibraryScan));
        EXPECT_TRUE(queue.isDue(start + seconds{ 160 }, Moment::DuringLibraryScan));
        EXPECT_EQ(queue.takeDue(start + seconds{ 160 }, Moment::DuringLibraryScan, 2), std::vector<std::filesystem::path>{ "/music/C" });
    }

} // namespace lms::scanner::tests
