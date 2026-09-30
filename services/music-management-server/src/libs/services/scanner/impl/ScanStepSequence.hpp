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
#include <functional>
#include <memory>
#include <optional>
#include <vector>

#include "PriorityFolderQueue.hpp"
#include "ScanContext.hpp"

#include "services/scanner/ScannerStats.hpp"

namespace lms::scanner
{
    class IScanStep;

    // Runs the scan steps from `startIndex` and returns the index it stopped at -- steps.size()
    // when everything ran, otherwise the index of the step that was interrupted. That return
    // value is what makes a pause resumable: handing it back in as `startIndex` re-runs the
    // interrupted step from its own beginning and leaves the earlier ones alone.
    //
    // `interrupted` is observed, never written: it is the same bool the steps themselves see,
    // and the caller decides what an interruption means.
    //
    // `betweenSteps`, when set, runs after every step that completed and before the next one:
    // the moment nothing of the scan is in flight, which is where a library-wide scan lets the
    // folders MuMa announced through (bug report 126). It does not run after the last step.
    std::size_t runScanSteps(std::vector<std::unique_ptr<IScanStep>>& steps,
                             ScanContext& context,
                             const bool& interrupted,
                             const std::function<void(const ScanStepStats&)>& notifyProgress,
                             std::size_t startIndex = 0,
                             const std::function<void()>& betweenSteps = {});

    // One priority pass inside a running library-wide scan (bug report 126): takes the folders
    // that are due at `now`, runs `steps` over them as an ordinary scoped scan and returns that
    // scan's context -- or nothing, when no folder was due. Progress is not reported: the status
    // keeps describing the library-wide scan.
    //
    // When `interrupted` goes up during the pass (an admin abort, a shutdown), the folders are
    // put back in `queue` rather than lost with the scan. The same goes for a step that throws;
    // the exception is rethrown once the folders are back.
    //
    // A pass reads at most `maxFoldersPerPriorityPass` folders (bug report 136). Its cost is mostly the
    // library-wide steps after the walk, the same for one folder as for fifty, but a tagger round
    // that announced hundreds would otherwise turn one pass into a small library scan of its own.
    // The rest stay queued, still due, for the next pass.
    inline constexpr std::size_t maxFoldersPerPriorityPass{ 50 };
    std::optional<ScanContext> runPriorityPass(std::vector<std::unique_ptr<IScanStep>>& steps,
                                               PriorityFolderQueue& queue,
                                               PriorityFolderQueue::Clock::time_point now,
                                               const bool& interrupted);
} // namespace lms::scanner
