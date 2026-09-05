/*
 * Copyright (C) 2013 Emeric Poupon
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
#include <memory>
#include <optional>
#include <shared_mutex>
#include <vector>

#include <boost/asio/steady_timer.hpp>
#include <boost/asio/system_timer.hpp>

#include <Wt/WDateTime.h>
#include <Wt/WIOService.h>
#include <Wt/WSignal.h>

#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "services/scanner/IScannerService.hpp"

#include "FileScanners.hpp"
#include "ScanContext.hpp"
#include "ScanRequestCollector.hpp"
#include "ScannerSettings.hpp"
#include "steps/IScanStep.hpp"

namespace lms::core
{
    class IJobScheduler;
}

namespace lms::scanner
{
    class IFileScanner;

    // Main goals to keepthe scanner fast:
    // - single pass on files: only 1 filesystem exploration must be done (no further reads triggered by parsed values)
    // - stable: 1 single scan (full or not) is enough: successive scans must have no effect if there is no change in the files
    class ScannerService : public IScannerService
    {
    public:
        ScannerService(db::IDb& db, const std::filesystem::path& cachePath);
        ~ScannerService() override;
        ScannerService(const ScannerService&) = delete;
        ScannerService& operator=(const ScannerService&) = delete;

    private:
        // Why a scan unwound. The steps only ever see the bool; this is what tells the service
        // whether to throw the run away or to keep it and come back to it.
        enum class InterruptReason
        {
            None,
            Abort,
            Pause,
        };

        // A periodic run that a scoped one interrupted, waiting to be resumed. The context
        // carries the stats of every step that already finished.
        struct PausedScan
        {
            ScanContext context;
            std::size_t stepIndex{};
        };

        void requestReload() override;
        void requestImmediateScan(const ScanOptions& scanOptions) override;
        void requestScopedScan(const std::vector<std::filesystem::path>& directories) override;

        Status getStatus() const override;
        Events& getEvents() override { return _events; }

        void start();
        void stop();

        // Job handling
        void scheduleNextScan();
        void scheduleScan(const ScanOptions& scanOptions, const Wt::WDateTime& dateTime = {});

        void abortScan();

        // Scoped request handling (all of this runs on the io thread)
        void armScanRequestTimer();
        void onScanRequestDue();
        void runPendingScopedScan();

        // Update database (scheduled callback)
        void scan(const ScanOptions& scanOptions);
        // Returns the index the run stopped at; see runScanSteps().
        std::size_t processScanSteps(ScanContext& context, std::size_t startIndex);

        void scanMediaDirectory(const std::filesystem::path& mediaDirectory, bool forceScan, ScanStats& stats);

        // Helpers
        void refreshScanSettings();
        void refreshTracingLoggerStats();

        void notifyInProgressIfNeeded(const ScanStepStats& stats);
        void notifyInProgress(const ScanStepStats& stats);

        db::IDb& _db;
        std::unique_ptr<core::IJobScheduler> _jobScheduler;
        const std::filesystem::path _cachePath;

        FileScanners _fileScanners;
        std::vector<std::unique_ptr<IScanStep>> _scanSteps;

        std::mutex _controlMutex;
        bool _abortScan{};
        InterruptReason _interruptReason{ InterruptReason::None };
        std::optional<PausedScan> _pausedScan;
        Wt::WIOService _ioService;
        boost::asio::system_timer _scheduleTimer{ _ioService };
        // Five seconds of quiet, and sixty seconds at the outside: a tagger round that touches
        // a folder every second would otherwise keep resetting the quiet period and its first
        // path would never be read.
        ScanRequestCollector _scanRequests{ std::chrono::seconds{ 5 }, std::chrono::seconds{ 60 } };
        boost::asio::steady_timer _scanRequestTimer{ _ioService };
        bool _firstSchedule{ true };
        Events _events;
        std::chrono::steady_clock::time_point _lastScanInProgressEmit;

        mutable std::shared_mutex _statusMutex;
        State _curState{ State::NotScheduled };
        std::optional<ScanStats> _lastCompleteScanStats;
        std::optional<ScanStepStats> _currentScanStepStats;
        Wt::WDateTime _nextScheduledScan;

        ScannerSettings _settings;
        std::optional<ScannerSettings> _lastScanSettings;
    };
} // namespace lms::scanner
