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

#pragma once

#include <Wt/WDateTime.h>
#include <Wt/WTime.h>

namespace lms::scanner
{
    // Mirrors db::ScanSettings::UpdatePeriod, so the arithmetic below stays a pure function
    // that a test can drive without a database.
    enum class ScanPeriod
    {
        Never,
        Daily,
        Weekly,
        Monthly,
        Hourly,
    };

    struct ScheduledScan
    {
        Wt::WDateTime dateTime; // invalid when nothing is scheduled
        bool fullScan{};
    };

    // The next moment the library-wide scan should start, and whether it re-reads every file.
    //
    // Two cadences run side by side: the incremental one (`period`) and the full re-read
    // (`fullScanPeriod`, weekly on `fullScanDayOfWeek`, 1..7 with Monday first). Whichever
    // comes first wins; on a tie the full one wins, because it does everything the
    // incremental does and running both would scan the library twice.
    ScheduledScan computeNextScan(ScanPeriod period,
                                  ScanPeriod fullScanPeriod,
                                  int fullScanDayOfWeek,
                                  Wt::WTime startTime,
                                  const Wt::WDateTime& now,
                                  bool firstSchedule);
} // namespace lms::scanner
