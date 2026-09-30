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

#include "database/WritePacer.hpp"

#include <thread>

namespace lms::db
{
    WritePacer::WritePacer(Settings settings, NowFunction now, SleepFunction sleep)
        : _settings{ settings }
        , _now{ now ? std::move(now) : NowFunction{ [] { return Clock::now(); } } }
        , _sleep{ sleep ? std::move(sleep) : SleepFunction{ [](Clock::duration duration) { std::this_thread::sleep_for(duration); } } }
    {
    }

    void WritePacer::onWriteBegin()
    {
        // A write transaction nested in an open one does not take the lock again.
        ++_depth;
        if (_depth > 1)
            return;

        const Clock::time_point now{ _now() };
        if (!_stretchStart || now - _lastEnd >= _settings.pause)
        {
            // The lock has been free for long enough since the last commit: whoever was waiting
            // had their chance, so this is a fresh stretch.
            _stretchStart = now;
            return;
        }

        if (now - *_stretchStart < _settings.maxStretch)
            return;

        _sleep(_settings.pause);
        ++_pauseCount;
        _totalPause += _settings.pause;
        _stretchStart = _now();
    }

    void WritePacer::onWriteEnd()
    {
        if (_depth == 0)
            return;

        --_depth;
        if (_depth > 0)
            return;

        _lastEnd = _now();
    }
} // namespace lms::db
