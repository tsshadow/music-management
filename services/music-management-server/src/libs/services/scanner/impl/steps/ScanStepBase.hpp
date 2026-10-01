/*
 * Copyright (C) 2023 Emeric Poupon
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

#include <functional>

#include "IPriorityScanYield.hpp"
#include "IScanStep.hpp"
#include "ScanErrorLogger.hpp"

namespace lms::core
{
    class IJobScheduler;
}

namespace lms::db
{
    class IDb;
}

namespace lms::scanner
{
    class FileScanners;
    struct ScannerSettings;
    struct ScanStepStats;
    struct ScanContext;
    struct ScanScope;

    class ScanStepBase : public IScanStep
    {
    public:
        using ProgressCallback = std::function<void(const ScanStepStats& stats)>;

        struct InitParams
        {
            core::IJobScheduler& jobScheduler;
            const ScannerSettings& settings;
            const ScannerSettings* lastScanSettings{};
            ProgressCallback progressCallback;
            bool& abortScan;
            db::IDb& db;
            const FileScanners& fileScanners;
            const std::filesystem::path& cachePath;
            // Null outside the service (tests), and never used by a step of a scoped scan.
            IPriorityScanYield* priorityYield{};
        };
        ScanStepBase(InitParams& initParams);
        ~ScanStepBase() override;
        ScanStepBase(const ScanStepBase&) = delete;
        ScanStepBase& operator=(const ScanStepBase&) = delete;

    protected:
        core::IJobScheduler& getJobScheduler() { return _jobScheduler; };
        const ScannerSettings* getLastScanSettings() const { return _lastScanSettings; }

        // Whether a library-wide scan has to recompute every release's artwork, and what falls
        // back on it (media, tracks, artists), because the release artwork rules differ from
        // the ones the last library-wide scan applied (bug report 144). Always false for a
        // scoped scan: it covers its own releases only and leaves the change to the next
        // library-wide one.
        bool releaseArtworkRulesChanged(const ScanContext& context) const;
        const FileScanners& getFileScanners() const { return _fileScanners; }
        const std::filesystem::path& getCachePath() const { return _cachePath; }

        void addError(ScanContext& context, std::shared_ptr<ScanError> error);

        // The part of the library a scoped scan has to recompute (see ScanScope), or null when
        // the step must cover the whole library: a library-wide scan, or a scoped one that
        // involves more than maxScopedTrackCount tracks. Computed on the first call of a scan and
        // kept in the context for the steps after it.
        const ScanScope* getScanScope(ScanContext& context);

        // See IPriorityScanYield for when a step may call these: only with nothing of its own in
        // flight on the job scheduler and no transaction open.
        bool isPriorityWorkDue() const { return _priorityYield && _priorityYield->isPriorityWorkDue(); }
        void runPriorityWork() const
        {
            if (_priorityYield)
                _priorityYield->runPriorityWork();
        }

        template<typename T, typename... CtrArgs>
        void addError(ScanContext& context, CtrArgs&&... args)
        {
            auto error{ std::make_shared<T>(std::forward<CtrArgs>(args)...) };
            addError(context, error);
        }

        const ScannerSettings& _settings;
        ProgressCallback _progressCallback;
        bool& _abortScan;
        db::IDb& _db;

    private:
        core::IJobScheduler& _jobScheduler;
        const FileScanners& _fileScanners;
        const std::filesystem::path& _cachePath;

        const ScannerSettings* _lastScanSettings{};
        IPriorityScanYield* _priorityYield{};
        ScanErrorLogger _scanErrorLogger;
    };
} // namespace lms::scanner
