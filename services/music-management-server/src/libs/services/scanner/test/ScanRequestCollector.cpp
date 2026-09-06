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

#include <gtest/gtest.h>

#include "ScanRequestCollector.hpp"

namespace lms::scanner::tests
{
    namespace
    {
        using Clock = ScanRequestCollector::Clock;
        constexpr std::chrono::seconds quietPeriod{ 5 };
        constexpr std::chrono::seconds maxDelay{ 60 };
        constexpr ScanRequestCollector::Timing timing{ .quietPeriod = quietPeriod, .maxDelay = maxDelay };
    } // namespace

    TEST(ScanRequestCollector, isEmptyAndHasNoDeadlineUntilSomethingArrives)
    {
        const ScanRequestCollector collector{ timing };

        EXPECT_TRUE(collector.empty());
        EXPECT_FALSE(collector.deadline().has_value());
    }

    TEST(ScanRequestCollector, mergesDuplicatePathsIntoOneRequest)
    {
        ScanRequestCollector collector{ timing };
        const Clock::time_point start{};

        collector.add({ "/music/A", "/music/B" }, start);
        collector.add({ "/music/A" }, start + std::chrono::seconds{ 1 });

        const std::vector<std::filesystem::path> taken{ collector.take() };
        EXPECT_EQ(taken.size(), 2);
        EXPECT_TRUE(collector.empty());
    }

    TEST(ScanRequestCollector, waitsForTheQuietPeriodAndEveryNewPathResetsIt)
    {
        ScanRequestCollector collector{ timing };
        const Clock::time_point start{};

        collector.add({ "/music/A" }, start);
        EXPECT_FALSE(collector.isDue(start + std::chrono::seconds{ 4 }));

        // A path arriving at t=4 pushes the quiet deadline out to t=9.
        collector.add({ "/music/B" }, start + std::chrono::seconds{ 4 });
        EXPECT_FALSE(collector.isDue(start + std::chrono::seconds{ 8 }));
        EXPECT_TRUE(collector.isDue(start + std::chrono::seconds{ 9 }));
    }

    TEST(ScanRequestCollector, firesAtTheHardCapEvenIfPathsKeepArriving)
    {
        // A tagger round touching a folder every second would otherwise reset the quiet
        // period forever and the first path would never be scanned.
        ScanRequestCollector collector{ timing };
        const Clock::time_point start{};

        for (int second{}; second < 70; ++second)
        {
            const Clock::time_point now{ start + std::chrono::seconds{ second } };
            collector.add({ "/music/A" }, now);
            if (second >= 60)
                EXPECT_TRUE(collector.isDue(now)) << "at second " << second;
            else
                EXPECT_FALSE(collector.isDue(now)) << "at second " << second;
        }
    }

    TEST(ScanRequestCollector, takeClearsTheStateSoTheNextBurstStartsItsOwnCycle)
    {
        ScanRequestCollector collector{ timing };
        const Clock::time_point start{};

        collector.add({ "/music/A" }, start);
        EXPECT_EQ(collector.take().size(), 1);
        EXPECT_TRUE(collector.empty());
        EXPECT_FALSE(collector.deadline().has_value());

        collector.add({ "/music/B" }, start + std::chrono::seconds{ 100 });
        EXPECT_FALSE(collector.isDue(start + std::chrono::seconds{ 102 }));
        EXPECT_TRUE(collector.isDue(start + std::chrono::seconds{ 105 }));
    }

    TEST(ScanRequestCollector, deadlineIsTheEarlierOfTheQuietPeriodAndTheCap)
    {
        ScanRequestCollector collector{ timing };
        const Clock::time_point start{};

        collector.add({ "/music/A" }, start);
        ASSERT_TRUE(collector.deadline().has_value());
        EXPECT_EQ(*collector.deadline(), start + std::chrono::seconds{ 5 });

        collector.add({ "/music/B" }, start + std::chrono::seconds{ 58 });
        EXPECT_EQ(*collector.deadline(), start + std::chrono::seconds{ 60 });
    }
} // namespace lms::scanner::tests
