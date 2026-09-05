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

#include <Wt/WDate.h>

#include <gtest/gtest.h>

#include "ScanSchedule.hpp"

namespace lms::scanner::tests
{
    namespace
    {
        const Wt::WTime threeAm{ 3, 0, 0 };
        // A Wednesday.
        const Wt::WDateTime wednesdayNoon{ Wt::WDate{ 2026, 9, 2 }, Wt::WTime{ 12, 0, 0 } };
        constexpr int sunday{ 7 }; // Wt::WDate::dayOfWeek() is 1..7, Monday first
    } // namespace

    TEST(ScanSchedule, neverSchedulesNothing)
    {
        const ScheduledScan next{ computeNextScan(ScanPeriod::Never, ScanPeriod::Never, sunday, threeAm, wednesdayNoon, false) };

        EXPECT_FALSE(next.dateTime.isValid());
    }

    TEST(ScanSchedule, dailyPicksTomorrowWhenTodaysTimeHasPassed)
    {
        const ScheduledScan next{ computeNextScan(ScanPeriod::Daily, ScanPeriod::Never, sunday, threeAm, wednesdayNoon, false) };

        EXPECT_EQ(next.dateTime, (Wt::WDateTime{ Wt::WDate{ 2026, 9, 3 }, threeAm }));
        EXPECT_FALSE(next.fullScan);
    }

    TEST(ScanSchedule, dailyPicksTodayWhenTheTimeIsStillAhead)
    {
        const Wt::WDateTime wednesdayOneAm{ Wt::WDate{ 2026, 9, 2 }, Wt::WTime{ 1, 0, 0 } };

        const ScheduledScan next{ computeNextScan(ScanPeriod::Daily, ScanPeriod::Never, sunday, threeAm, wednesdayOneAm, false) };

        EXPECT_EQ(next.dateTime, (Wt::WDateTime{ Wt::WDate{ 2026, 9, 2 }, threeAm }));
    }

    TEST(ScanSchedule, theWeeklyFullScanIsScheduledOnItsOwnDay)
    {
        // Sunday 2026-09-06 is the first Sunday after Wednesday the 2nd.
        const ScheduledScan next{ computeNextScan(ScanPeriod::Never, ScanPeriod::Weekly, sunday, threeAm, wednesdayNoon, false) };

        EXPECT_EQ(next.dateTime, (Wt::WDateTime{ Wt::WDate{ 2026, 9, 6 }, threeAm }));
        EXPECT_TRUE(next.fullScan);
    }

    TEST(ScanSchedule, theFullScanWinsWhenBothFallOnTheSameMoment)
    {
        // Saturday: the daily lands on Sunday 03:00 and so does the weekly full one. Running
        // both would mean scanning the library twice; the full one does everything the
        // incremental does.
        const Wt::WDateTime saturdayNoon{ Wt::WDate{ 2026, 9, 5 }, Wt::WTime{ 12, 0, 0 } };

        const ScheduledScan next{ computeNextScan(ScanPeriod::Daily, ScanPeriod::Weekly, sunday, threeAm, saturdayNoon, false) };

        EXPECT_EQ(next.dateTime, (Wt::WDateTime{ Wt::WDate{ 2026, 9, 6 }, threeAm }));
        EXPECT_TRUE(next.fullScan);
    }

    TEST(ScanSchedule, theIncrementalWinsWhenItComesFirst)
    {
        const ScheduledScan next{ computeNextScan(ScanPeriod::Daily, ScanPeriod::Weekly, sunday, threeAm, wednesdayNoon, false) };

        EXPECT_EQ(next.dateTime, (Wt::WDateTime{ Wt::WDate{ 2026, 9, 3 }, threeAm }));
        EXPECT_FALSE(next.fullScan);
    }

    TEST(ScanSchedule, hourlyRunsImmediatelyOnTheFirstSchedule)
    {
        const ScheduledScan next{ computeNextScan(ScanPeriod::Hourly, ScanPeriod::Never, sunday, threeAm, wednesdayNoon, true) };

        EXPECT_EQ(next.dateTime, wednesdayNoon);
    }

    TEST(ScanSchedule, hourlyAddsAnHourAfterwards)
    {
        const ScheduledScan next{ computeNextScan(ScanPeriod::Hourly, ScanPeriod::Never, sunday, threeAm, wednesdayNoon, false) };

        EXPECT_EQ(next.dateTime, (Wt::WDateTime{ Wt::WDate{ 2026, 9, 2 }, Wt::WTime{ 13, 0, 0 } }));
    }

    TEST(ScanSchedule, hourlyCrossesMidnightIntoTheNextDay)
    {
        // The old arithmetic added an hour to the WTime alone, so 23:30 wrapped to 00:30 on
        // the same day and the next scan was scheduled in the past.
        const Wt::WDateTime lateEvening{ Wt::WDate{ 2026, 9, 2 }, Wt::WTime{ 23, 30, 0 } };

        const ScheduledScan next{ computeNextScan(ScanPeriod::Hourly, ScanPeriod::Never, sunday, threeAm, lateEvening, false) };

        EXPECT_EQ(next.dateTime, (Wt::WDateTime{ Wt::WDate{ 2026, 9, 3 }, Wt::WTime{ 0, 30, 0 } }));
    }
} // namespace lms::scanner::tests
