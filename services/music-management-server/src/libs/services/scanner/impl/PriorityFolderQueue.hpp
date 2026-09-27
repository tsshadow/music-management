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

#include <cstddef>
#include <filesystem>
#include <mutex>
#include <optional>
#include <vector>

#include "ScanRequestCollector.hpp"

namespace lms::scanner
{
    // The folders MuMa announced (startScan with `path`), waiting to be read, shared between the
    // web threads that add them and the scanner thread that takes them.
    //
    // They used to live in a ScanRequestCollector that only the scanner's io thread touched. That
    // is the same single thread that runs scan(), so while a library-wide scan ran -- well over an
    // hour on production -- nothing could add a path, fire the debounce timer or ask the scan to
    // make room: a new download stayed invisible until the whole library had been walked (bug
    // report 126). Guarding the collector with a mutex lets the running scan look at it itself.
    //
    // Two ways out:
    // - takeDue(now, Idle): nothing else runs, the folders leave as soon as the collector's
    //   debounce says so, as they always did;
    // - takeDue(now, DuringLibraryScan): a library-wide scan reached a point where it can let a
    //   priority pass run. The same debounce applies, plus a minimum gap after the previous pass,
    //   so a tagger that touches a folder every few seconds cannot turn the library-wide scan
    //   into a string of priority passes.
    //
    // Time is a parameter, never read from the clock here, so the whole thing is testable without
    // sleeping.
    class PriorityFolderQueue
    {
    public:
        using Clock = ScanRequestCollector::Clock;

        struct Timing
        {
            ScanRequestCollector::Timing collect;
            // How long the library-wide scan gets to itself after a priority pass ends.
            Clock::duration minGapDuringLibraryScan;
        };

        enum class Moment
        {
            Idle,
            DuringLibraryScan,
        };

        explicit PriorityFolderQueue(Timing timing);

        void add(const std::vector<std::filesystem::path>& paths, Clock::time_point now);

        // When the pending folders become due while the scanner is idle, or nothing when there
        // are none. What the io thread arms its timer with.
        std::optional<Clock::time_point> deadline() const;
        std::size_t pendingCount() const;

        bool isDue(Clock::time_point now, Moment moment) const;

        // Hands out the pending folders if they are due at `moment`, otherwise nothing.
        std::vector<std::filesystem::path> takeDue(Clock::time_point now, Moment moment);
        // Hands out whatever is pending, due or not: the idle timer fired.
        std::vector<std::filesystem::path> take();

        // A priority pass inside a library-wide scan ended; starts the gap.
        void priorityPassFinished(Clock::time_point now);

    private:
        bool isDueLocked(Clock::time_point now, Moment moment) const;

        const Clock::duration _minGapDuringLibraryScan;

        mutable std::mutex _mutex;
        ScanRequestCollector _collector;
        std::optional<Clock::time_point> _lastPriorityPassEnd;
    };
} // namespace lms::scanner
