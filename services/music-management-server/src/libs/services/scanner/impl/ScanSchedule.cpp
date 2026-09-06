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

#include "ScanSchedule.hpp"

#include <Wt/WDate.h>

namespace lms::scanner
{
    namespace
    {
        constexpr int firstDayOfMonth{ 1 };
        constexpr int secondsPerHour{ 3600 };

        Wt::WDate getNextDayOfWeek(Wt::WDate current, int dayOfWeek)
        {
            current = current.addDays(1);
            while (current.dayOfWeek() != dayOfWeek)
                current = current.addDays(1);

            return current;
        }

        Wt::WDate getNextFirstOfMonth(Wt::WDate current)
        {
            current = current.addDays(1);
            while (current.day() != firstDayOfMonth)
                current = current.addDays(1);

            return current;
        }

        Wt::WDateTime nextMoment(ScanPeriod period, int dayOfWeek, Wt::WTime startTime, const Wt::WDateTime& now, bool firstSchedule)
        {
            switch (period)
            {
            case ScanPeriod::Never:
                break;

            case ScanPeriod::Daily:
                if (now.time() < startTime)
                    return { now.date(), startTime };
                return { now.date().addDays(1), startTime };

            case ScanPeriod::Weekly:
                if (now.time() < startTime && now.date().dayOfWeek() == dayOfWeek)
                    return { now.date(), startTime };
                return { getNextDayOfWeek(now.date(), dayOfWeek), startTime };

            case ScanPeriod::Monthly:
                if (now.time() < startTime && now.date().day() == firstDayOfMonth)
                    return { now.date(), startTime };
                return { getNextFirstOfMonth(now.date()), startTime };

            case ScanPeriod::Hourly:
                if (firstSchedule)
                    return now;
                // addSecs on the whole date/time, not on the WTime: adding an hour to 23:30
                // used to wrap the time around and keep the date, scheduling the next scan
                // in the past.
                return now.addSecs(secondsPerHour);
            }

            return {};
        }
    } // namespace

    ScheduledScan computeNextScan(ScanPeriod period, ScanPeriod fullScanPeriod, int fullScanDayOfWeek, Wt::WTime startTime, const Wt::WDateTime& now, bool firstSchedule)
    {
        // The incremental weekly cadence keeps its historical day: Monday.
        const Wt::WDateTime incremental{ nextMoment(period, 1, startTime, now, firstSchedule) };
        const Wt::WDateTime full{ nextMoment(fullScanPeriod, fullScanDayOfWeek, startTime, now, false) };

        if (!full.isValid())
            return { incremental, false };
        if (!incremental.isValid())
            return { full, true };

        // On a tie the full scan wins: it does everything the incremental one does.
        return incremental < full ? ScheduledScan{ incremental, false } : ScheduledScan{ full, true };
    }
} // namespace lms::scanner
