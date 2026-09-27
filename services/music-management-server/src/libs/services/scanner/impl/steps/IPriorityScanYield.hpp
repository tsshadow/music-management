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

namespace lms::scanner
{
    // How a long-running step of a library-wide scan lets the folders MuMa announced jump the
    // queue (bug report 126). The scan does not stop or restart for them: at a point where it is
    // safe, it runs a priority pass over those folders -- the ordinary scoped scan, on this same
    // thread -- and then carries on where it was.
    //
    // "Safe" is the caller's promise, and it is a strict one: nothing the caller started may still
    // be in flight. No job of its own queued on the job scheduler (the pass schedules its own, and
    // JobQueue assumes it owns the scheduler), and no transaction open (the pass takes the
    // database write lock batch by batch, like any scan).
    class IPriorityScanYield
    {
    public:
        virtual ~IPriorityScanYield() = default;

        // Cheap enough to ask every few files: a mutex and a clock read.
        virtual bool isPriorityWorkDue() = 0;
        // Runs the pending folders now. Returns when the pass is done.
        virtual void runPriorityWork() = 0;
    };
} // namespace lms::scanner
