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
                             const bool& interrupted,
                             const std::function<void(const ScanStepStats&)>& notifyProgress,
                             std::size_t startIndex,
                             const std::function<void()>& betweenSteps)
    {
        for (std::size_t stepIndex{ startIndex }; stepIndex < steps.size(); ++stepIndex)
        {
            auto& scanStep{ steps.at(stepIndex) };

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

            if (betweenSteps && stepIndex + 1 < steps.size())
                betweenSteps();
        }

        return steps.size();
    }

    std::optional<ScanContext> runPriorityPass(std::vector<std::unique_ptr<IScanStep>>& steps,
                                               PriorityFolderQueue& queue,
                                               PriorityFolderQueue::Clock::time_point now,
                                               const bool& interrupted)
    {
        std::vector<std::filesystem::path> folders{ queue.takeDue(now, PriorityFolderQueue::Moment::DuringLibraryScan, maxFoldersPerPriorityPass) };
        if (folders.empty())
            return std::nullopt;

        ScanContext context;
        context.scanOptions.scanDirectories = std::move(folders);
        context.stats.startTime = Wt::WDateTime::currentDateTime();

        try
        {
            runScanSteps(steps, context, interrupted, [](const ScanStepStats&) {});
        }
        catch (...)
        {
            // A step that throws -- a database still locked past busy_timeout (bug report
            // 132) -- ends the pass as surely as an interruption, and the folders were
            // taken off the queue already. The caller decides what the exception means.
            queue.add(context.scanOptions.scanDirectories, now);
            throw;
        }

        if (interrupted)
            queue.add(context.scanOptions.scanDirectories, now);
        else
            context.stats.stopTime = Wt::WDateTime::currentDateTime();

        return context;
    }
} // namespace lms::scanner
