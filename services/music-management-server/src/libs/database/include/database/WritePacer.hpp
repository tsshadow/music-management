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
#include <cstddef>
#include <functional>
#include <optional>

namespace lms::db
{
    // Makes a bulk writer -- the scanner -- hand the database write lock to other writers now and
    // then (bug report 134).
    //
    // Committing often is not enough on its own. A loop of short write transactions gives the lock
    // back for microseconds between two of them, and no other writer gets in: music-manager's
    // connection (and an LMS request thread going through SQLite's busy handler) sleeps up to
    // 100 ms between two attempts at the lock, and an LMS thread blocked on the in-process write
    // mutex loses the race to the thread that just unlocked it. On production the WAL write lock
    // was seen held in 5,853 of 5,855 samples 5 ms apart, in runs of up to 19.6 s, while every
    // single transaction was short.
    //
    // So the pacer measures how long its thread has been writing without a real break: a stretch
    // starts at a write transaction, and ends at a gap of at least `pause` since the previous one
    // was committed. Once a stretch is `maxStretch` long, the next write transaction first sleeps
    // for `pause`, with the lock released. `pause` is chosen longer than the longest sleep of
    // SQLite's default busy handler (100 ms), so a waiting connection is certain to try the lock
    // at least once inside the gap. Nothing about a single transaction changes: one that is
    // already open is never interrupted, and a nested write transaction is not paced.
    //
    // One pacer per thread: it belongs to that thread's db::Session and is not synchronised.
    class WritePacer
    {
    public:
        using Clock = std::chrono::steady_clock;

        struct Settings
        {
            std::chrono::milliseconds maxStretch{ 500 };
            std::chrono::milliseconds pause{ 120 };
        };

        using NowFunction = std::function<Clock::time_point()>;
        using SleepFunction = std::function<void(Clock::duration)>;

        // `now` and `sleep` are there for the tests; the defaults are the steady clock and
        // std::this_thread::sleep_for.
        explicit WritePacer(Settings settings, NowFunction now = {}, SleepFunction sleep = {});

        // Called by WriteTransaction before it takes the write mutex, and after it gave it back.
        void onWriteBegin();
        void onWriteEnd();

        // How often, and for how long in total, this pacer has held its thread back.
        std::size_t getPauseCount() const { return _pauseCount; }
        Clock::duration getTotalPause() const { return _totalPause; }

        const Settings& getSettings() const { return _settings; }

    private:
        const Settings _settings;
        const NowFunction _now;
        const SleepFunction _sleep;

        std::size_t _depth{};
        std::optional<Clock::time_point> _stretchStart;
        Clock::time_point _lastEnd;
        std::size_t _pauseCount{};
        Clock::duration _totalPause{};
    };
} // namespace lms::db
