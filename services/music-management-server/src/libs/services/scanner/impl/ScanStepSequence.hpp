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
#include <vector>

#include "services/scanner/ScannerStats.hpp"

namespace lms::scanner
{
    struct ScanContext;
    class IScanStep;

    // Runs the scan steps from `startIndex` and returns the index it stopped at -- steps.size()
    // when everything ran, otherwise the index of the step that was interrupted. That return
    // value is what makes a pause resumable: handing it back in as `startIndex` re-runs the
    // interrupted step from its own beginning and leaves the earlier ones alone.
    //
    // `interrupted` is observed, never written: it is the same bool the steps themselves see,
    // and the caller decides what an interruption means.
    std::size_t runScanSteps(std::vector<std::unique_ptr<IScanStep>>& steps,
                             ScanContext& context,
                             std::size_t startIndex,
                             const bool& interrupted,
                             const std::function<void(const ScanStepStats&)>& notifyProgress);
} // namespace lms::scanner
