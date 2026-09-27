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

#include "services/scanner/ScannerOptions.hpp"

namespace lms::scanner
{
    // What the scanner is doing at the moment a library-wide scan request arrives.
    struct RunningScan
    {
        bool inProgress{};        // a scan() is running on the scanner thread
        bool scoped{};            // ... and it only reads a handful of folders
        bool libraryScanPaused{}; // a library-wide run is parked, waiting for the scoped one to end
    };

    // What happens to a library-wide ("rescan everything that changed") request.
    enum class ImmediateScanDecision
    {
        // Abort whatever runs and start the requested scan now. The only answer there used to be.
        Start,
        // A library-wide scan is already walking the library, which is what was asked for.
        Absorb,
        // A scoped scan is running; the library-wide one runs as soon as that ends.
        QueueAfterCurrent,
    };

    // Starting over used to be the answer to every request, and it had two costs. The HTTP thread
    // that asked waited in abortScan() until the running scan reached a batch boundary, which is
    // what timed MuMa's scan trigger out at ten seconds. And the running scan was thrown away: the
    // tagger asked every ~5 minutes, a library-wide scan here takes the better part of an hour, so
    // no library-wide scan -- periodic or requested -- could ever finish (bug report 120).
    //
    // A plain request now joins what is already running. A request that asks for something the
    // running scan will not do (fullScan, forceOptimize, compact) still starts over, as before:
    // that is an admin action, rare, and means "do it this way, now".
    //
    // What an absorbed request gives up: folders the running walk has already passed are not
    // re-read for it. MuMa announces those folders itself (the scoped `path` request), and the
    // next periodic scan covers anything nobody announced.
    ImmediateScanDecision decideImmediateScan(const ScanOptions& request, const RunningScan& running);
} // namespace lms::scanner
