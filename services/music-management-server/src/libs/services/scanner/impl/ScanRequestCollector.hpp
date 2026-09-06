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

#include <chrono>
#include <filesystem>
#include <optional>
#include <set>
#include <vector>

namespace lms::scanner
{
    // Collects scan scopes that arrive from the API and decides when they leave as one job.
    //
    // MuMa moves and retags in bulk, and every interruption costs the periodic scan the step
    // it was in. Merging a burst into a single request is what keeps that cost at one step
    // per burst instead of one per file. The hard cap exists because a steady stream would
    // otherwise reset the quiet period forever and the first path would never be read.
    //
    // Time is a parameter, never read from the clock here, so the whole thing is testable
    // without sleeping.
    class ScanRequestCollector
    {
    public:
        using Clock = std::chrono::steady_clock;

        // Both are durations, and swapping them turns a five-second debounce with a
        // one-minute cap into the reverse without the compiler noticing. Naming them at
        // the call site is the only thing that catches that.
        struct Timing
        {
            Clock::duration quietPeriod;
            Clock::duration maxDelay;
        };

        explicit ScanRequestCollector(Timing timing);

        void add(const std::vector<std::filesystem::path>& paths, Clock::time_point now);
        bool empty() const { return _paths.empty(); }

        // When the pending paths should leave, or nothing when there are none.
        std::optional<Clock::time_point> deadline() const;
        bool isDue(Clock::time_point now) const;

        // Hands out the pending paths and resets the cycle.
        std::vector<std::filesystem::path> take();

    private:
        const Clock::duration _quietPeriod;
        const Clock::duration _maxDelay;

        std::set<std::filesystem::path> _paths;
        Clock::time_point _firstAdded;
        Clock::time_point _lastAdded;
    };
} // namespace lms::scanner
