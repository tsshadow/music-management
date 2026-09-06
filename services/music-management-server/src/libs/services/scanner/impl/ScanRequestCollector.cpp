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

#include "ScanRequestCollector.hpp"

#include <algorithm>

namespace lms::scanner
{
    ScanRequestCollector::ScanRequestCollector(Timing timing)
        : _quietPeriod{ timing.quietPeriod }
        , _maxDelay{ timing.maxDelay }
    {
    }

    void ScanRequestCollector::add(const std::vector<std::filesystem::path>& paths, Clock::time_point now)
    {
        if (paths.empty())
            return;

        if (_paths.empty())
            _firstAdded = now;
        _lastAdded = now;

        _paths.insert(std::cbegin(paths), std::cend(paths));
    }

    std::optional<ScanRequestCollector::Clock::time_point> ScanRequestCollector::deadline() const
    {
        if (_paths.empty())
            return std::nullopt;

        return std::min(_lastAdded + _quietPeriod, _firstAdded + _maxDelay);
    }

    bool ScanRequestCollector::isDue(Clock::time_point now) const
    {
        const std::optional<Clock::time_point> when{ deadline() };
        return when && now >= *when;
    }

    std::vector<std::filesystem::path> ScanRequestCollector::take()
    {
        std::vector<std::filesystem::path> res{ std::cbegin(_paths), std::cend(_paths) };
        _paths.clear();
        return res;
    }
} // namespace lms::scanner
