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

#include "PriorityFolderQueue.hpp"

namespace lms::scanner
{
    PriorityFolderQueue::PriorityFolderQueue(Timing timing)
        : _minGapDuringLibraryScan{ timing.minGapDuringLibraryScan }
        , _collector{ timing.collect }
    {
    }

    void PriorityFolderQueue::add(const std::vector<std::filesystem::path>& paths, Clock::time_point now)
    {
        const std::scoped_lock lock{ _mutex };
        _collector.add(paths, now);
    }

    std::optional<PriorityFolderQueue::Clock::time_point> PriorityFolderQueue::deadline() const
    {
        const std::scoped_lock lock{ _mutex };
        return _collector.deadline();
    }

    std::size_t PriorityFolderQueue::pendingCount() const
    {
        const std::scoped_lock lock{ _mutex };
        return _collector.size();
    }

    bool PriorityFolderQueue::isDue(Clock::time_point now, Moment moment) const
    {
        const std::scoped_lock lock{ _mutex };
        return isDueLocked(now, moment);
    }

    std::vector<std::filesystem::path> PriorityFolderQueue::takeDue(Clock::time_point now, Moment moment)
    {
        const std::scoped_lock lock{ _mutex };
        if (!isDueLocked(now, moment))
            return {};

        return _collector.take();
    }

    std::vector<std::filesystem::path> PriorityFolderQueue::take()
    {
        const std::scoped_lock lock{ _mutex };
        return _collector.take();
    }

    void PriorityFolderQueue::priorityPassFinished(Clock::time_point now)
    {
        const std::scoped_lock lock{ _mutex };
        _lastPriorityPassEnd = now;
    }

    bool PriorityFolderQueue::isDueLocked(Clock::time_point now, Moment moment) const
    {
        if (!_collector.isDue(now))
            return false;

        if (moment == Moment::DuringLibraryScan && _lastPriorityPassEnd && now < *_lastPriorityPassEnd + _minGapDuringLibraryScan)
            return false;

        return true;
    }
} // namespace lms::scanner
