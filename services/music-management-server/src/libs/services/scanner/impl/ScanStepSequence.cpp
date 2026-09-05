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

#include "ScanStepSequence.hpp"

#include <Wt/WDateTime.h>

#include "core/ILogger.hpp"
#include "core/ITraceLogger.hpp"

#include "ScanContext.hpp"
#include "steps/IScanStep.hpp"

namespace lms::scanner
{
    std::size_t runScanSteps(std::vector<std::unique_ptr<IScanStep>>& steps,
                             ScanContext& context,
                             std::size_t startIndex,
                             const bool& interrupted,
                             const std::function<void(const ScanStepStats&)>& notifyProgress)
    {
        for (std::size_t stepIndex{ startIndex }; stepIndex < steps.size(); ++stepIndex)
        {
            auto& scanStep{ steps[stepIndex] };

            context.currentStepStats = ScanStepStats{
                .startTime = Wt::WDateTime::currentDateTime(),
                .stepCount = steps.size(),
                .stepIndex = stepIndex,
                .currentStep = scanStep->getStep(),
                .totalElems = 0,
                .processedElems = 0
            };

            if (interrupted)
                return stepIndex;

            if (!scanStep->needProcess(context))
            {
                LMS_LOG(DBUPDATER, DEBUG, "Skipping scan step '" << scanStep->getStepName() << "'");
                continue;
            }

            {
                LMS_SCOPED_TRACE_OVERVIEW("Scanner", scanStep->getStepName());

                LMS_LOG(DBUPDATER, DEBUG, "Starting scan step '" << scanStep->getStepName() << "'");
                notifyProgress(context.currentStepStats);
                scanStep->process(context);
                notifyProgress(context.currentStepStats);
                LMS_LOG(DBUPDATER, DEBUG, "Completed scan step '" << scanStep->getStepName() << "'");
            }

            // A step that unwound because the flag went up mid-batch has not finished its work.
            if (interrupted)
                return stepIndex;
        }

        return steps.size();
    }
} // namespace lms::scanner
