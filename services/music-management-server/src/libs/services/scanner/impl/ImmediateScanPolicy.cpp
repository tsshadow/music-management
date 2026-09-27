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

#include "ImmediateScanPolicy.hpp"

namespace lms::scanner
{
    namespace
    {
        bool isPlainLibraryScan(const ScanOptions& options)
        {
            return !options.fullScan && !options.forceOptimize && !options.compact && !options.isScoped();
        }
    } // namespace

    ImmediateScanDecision decideImmediateScan(const ScanOptions& request, const RunningScan& running)
    {
        if (!isPlainLibraryScan(request))
            return ImmediateScanDecision::Start;

        if (running.inProgress && !running.scoped)
            return ImmediateScanDecision::Absorb;

        if (running.inProgress)
            return ImmediateScanDecision::QueueAfterCurrent;

        return ImmediateScanDecision::Start;
    }
} // namespace lms::scanner
