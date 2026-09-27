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

#include "ScannerService.hpp"

#include "ImmediateScanPolicy.hpp"
#include "ScanErrorPolicy.hpp"
#include "ScanSchedule.hpp"
#include "ScanStepSequence.hpp"

#include <ctime>

#include <Wt/WDate.h>

#include "core/IConfig.hpp"
#include "core/IJobScheduler.hpp"
#include "core/ILogger.hpp"
#include "core/ITraceLogger.hpp"

#include "database/Session.hpp"
#include "database/objects/MediaLibrary.hpp"
#include "database/objects/ScanSettings.hpp"

#include "scanners/ImageFileScanner.hpp"
#include "scanners/artistinfo/ArtistInfoFileScanner.hpp"
#include "scanners/audiofile/AudioFileScanner.hpp"
#include "scanners/lyrics/LyricsFileScanner.hpp"
#include "scanners/playlist/PlayListFileScanner.hpp"

#include "steps/ScanStepArtistReconciliation.hpp"
#include "steps/ScanStepAssociateArtistImages.hpp"
#include "steps/ScanStepAssociateExternalLyrics.hpp"
#include "steps/ScanStepAssociateMediumImages.hpp"
#include "steps/ScanStepAssociatePlayListTracks.hpp"
#include "steps/ScanStepAssociateReleaseImages.hpp"
#include "steps/ScanStepAssociateTrackImages.hpp"
#include "steps/ScanStepCheckForDuplicatedFiles.hpp"
#include "steps/ScanStepCheckForRemovedFiles.hpp"
#include "steps/ScanStepCompact.hpp"
#include "steps/ScanStepComputeClusterStats.hpp"
#include "steps/ScanStepOptimize.hpp"
#include "steps/ScanStepRemoveOrphanedDbEntries.hpp"
#include "steps/ScanStepScanFiles.hpp"
#include "steps/ScanStepUpdateLibraryFields.hpp"

#include "ScanContext.hpp"

namespace lms::scanner
{
    using namespace db;

    namespace
    {
        constexpr std::string_view currentSettingsName{};
        constexpr std::string_view lastScanSettingsName{ "last_scan" };

        ScanPeriod toScanPeriod(db::ScanSettings::UpdatePeriod period)
        {
            switch (period)
            {
            case db::ScanSettings::UpdatePeriod::Never:
                break;
            case db::ScanSettings::UpdatePeriod::Daily:
                return ScanPeriod::Daily;
            case db::ScanSettings::UpdatePeriod::Weekly:
                return ScanPeriod::Weekly;
            case db::ScanSettings::UpdatePeriod::Monthly:
                return ScanPeriod::Monthly;
            case db::ScanSettings::UpdatePeriod::Hourly:
                return ScanPeriod::Hourly;
            }

            return ScanPeriod::Never;
        }

        ScanPeriod toScanPeriod(db::ScanSettings::FullScanPeriod period)
        {
            return period == db::ScanSettings::FullScanPeriod::Weekly ? ScanPeriod::Weekly : ScanPeriod::Never;
        }

        std::optional<ScannerSettings> readScannerSettings(db::Session& session, std::string_view name)
        {
            std::optional<ScannerSettings> settings;

            auto transaction{ session.createReadTransaction() };

            const ScanSettings::pointer scanSettings{ ScanSettings::find(session, name) };
            if (!scanSettings)
                return settings;

            settings.emplace();
            settings->audioScanVersion = scanSettings->getAudioScanVersion();
            settings->artistInfoScanVersion = scanSettings->getArtistInfoScanVersion();
            settings->startTime = scanSettings->getUpdateStartTime();
            settings->updatePeriod = scanSettings->getUpdatePeriod();

            MediaLibrary::find(session, [&](const MediaLibrary::pointer& mediaLibrary) {
                MediaLibraryInfo info;
                info.firstScan = mediaLibrary->isEmpty();
                info.id = mediaLibrary->getId();
                info.rootDirectory = mediaLibrary->getPath().lexically_normal();

                settings->mediaLibraries.push_back(info);
            });

            {
                const auto& tags{ scanSettings->getExtraTagsToScan() };
                std::transform(std::cbegin(tags), std::cend(tags), std::back_inserter(settings->extraTags), [](std::string_view tag) { return std::string{ tag }; });
            }

            settings->artistTagDelimiters = scanSettings->getArtistTagDelimiters();
            settings->defaultTagDelimiters = scanSettings->getDefaultTagDelimiters();
            settings->artistsToNotSplit = scanSettings->getArtistsToNotSplit();

            settings->skipSingleReleasePlayLists = scanSettings->getSkipSingleReleasePlayLists();
            settings->allowArtistMBIDFallback = scanSettings->getAllowMBIDArtistMerge();
            settings->artistImageFallbackToRelease = scanSettings->getArtistImageFallbackToReleaseField();

            // TODO, store this in DB + expose in UI
            settings->skipDuplicateTrackMBID = core::Service<core::IConfig>::get()->getBool("scanner-skip-duplicate-mbid", false);

            return settings;
        }

        void writeScannerSettings(db::Session& session, std::string_view name, const ScannerSettings& settings)
        {
            auto transaction{ session.createWriteTransaction() };

            ScanSettings::pointer scanSettings{ ScanSettings::find(session, name) };
            if (!scanSettings)
                scanSettings = session.create<ScanSettings>(name);

            scanSettings.modify()->setAllowMBIDArtistMerge(settings.allowArtistMBIDFallback);
            scanSettings.modify()->setSkipSingleReleasePlayLists(settings.skipSingleReleasePlayLists);
            // TODO add more fields
        }

        std::size_t getScannerThreadCount()
        {
            std::size_t threadCount{ core::Service<core::IConfig>::get()->getULong("scanner-thread-count", 0) };

            if (threadCount == 0)
                threadCount = std::max<std::size_t>(std::thread::hardware_concurrency() / 2, 1);

            return threadCount;
        }

    } // namespace

    std::unique_ptr<IScannerService> createScannerService(db::IDb& db, const std::filesystem::path& cachePath)
    {
        return std::make_unique<ScannerService>(db, cachePath);
    }

    ScannerService::ScannerService(db::IDb& db, const std::filesystem::path& cachePath)
        : _db{ db }
        , _jobScheduler{ core::createJobScheduler("Scanner", getScannerThreadCount()) }
        , _cachePath{ cachePath }
    {
        _ioService.setThreadCount(1);

        LMS_LOG(DBUPDATER, INFO, "Using " << _jobScheduler->getThreadCount() << " thread(s) for jobs");
        _jobScheduler->setShouldAbortCallback([this]() { return _abortScan; });

        std::size_t totalFileCount{};
        {
            auto& session{ _db.getTLSSession() };
            auto transaction{ session.createReadTransaction() };
            totalFileCount = session.getFileStats().getTotalFileCount();
        }

        // Force optimize in case scanner aborted during a large import, but do this only if there are enough elements in the database
        // Otherwise, indexes may be not used and queries may be slower and slower while adding more and more elements in the db
        LMS_LOG(DBUPDATER, INFO, "Scanned file count = " << totalFileCount);
        if (totalFileCount >= 1'000)
            _db.getTLSSession().fullAnalyze();

        refreshTracingLoggerStats();
        refreshScanSettings();

        start();
    }

    ScannerService::~ScannerService()
    {
        LMS_LOG(DBUPDATER, INFO, "Stopping service...");
        stop();
        LMS_LOG(DBUPDATER, INFO, "Service stopped!");
    }

    void ScannerService::start()
    {
        std::scoped_lock lock{ _controlMutex };

        _ioService.post([this] {
            if (_abortScan)
                return;

            scheduleNextScan();
        });

        _ioService.start();
    }

    void ScannerService::stop()
    {
        std::scoped_lock lock{ _controlMutex };

        _abortScan = true;
        _scheduleTimer.cancel();
        _ioService.stop();
    }

    void ScannerService::abortScan()
    {
        bool isRunning{};
        {
            std::scoped_lock lock{ _statusMutex };
            isRunning = _curState == State::InProgress;
        }

        LMS_LOG(DBUPDATER, DEBUG, "Aborting scan...");
        std::scoped_lock lock{ _controlMutex };

        LMS_LOG(DBUPDATER, DEBUG, "Waiting for the scan to abort...");

        _interruptReason = InterruptReason::Abort;
        _abortScan = true;
        _scheduleTimer.cancel();
        _ioService.stop();
        LMS_LOG(DBUPDATER, DEBUG, "Scan abort done!");

        _abortScan = false;
        _interruptReason = InterruptReason::None;
        setPausedScan(std::nullopt); // an aborted run is thrown away, paused or not
        _ioService.start();

        if (isRunning)
            _events.scanAborted.emit();
    }

    void ScannerService::setPausedScan(std::optional<PausedScan> pausedScan)
    {
        _pausedScan = std::move(pausedScan);

        const std::unique_lock lock{ _statusMutex };
        _libraryScanPaused = _pausedScan.has_value();
    }

    void ScannerService::requestImmediateScan(const ScanOptions& scanOptions)
    {
        // Called from a Wt web thread. Starting over means abortScan(), which waits on this
        // thread until the running scan unwinds; see ImmediateScanPolicy for why a plain request
        // no longer does that.
        {
            const std::unique_lock lock{ _statusMutex };
            const RunningScan running{ .inProgress = _scanRunning, .scoped = _scanRunningScoped, .libraryScanPaused = _libraryScanPaused };
            switch (decideImmediateScan(scanOptions, running))
            {
            case ImmediateScanDecision::Absorb:
                LMS_LOG(DBUPDATER, INFO, "Library scan requested while one is running: joining it");
                return;
            case ImmediateScanDecision::QueueAfterCurrent:
                _libraryScanQueued = true;
                LMS_LOG(DBUPDATER, INFO, "Library scan requested during a scoped scan: queued after it");
                return;
            case ImmediateScanDecision::Start:
                break;
            }
        }

        abortScan();
        _ioService.post([this, scanOptions] {
            if (_abortScan)
                return;

            scheduleScan(scanOptions);
        });
    }

    void ScannerService::requestScopedScan(const std::vector<std::filesystem::path>& directories)
    {
        // Called from a Wt web thread; everything below runs on the io thread.
        _ioService.post([this, directories] {
            _scanRequests.add(directories, ScanRequestCollector::Clock::now());
            armScanRequestTimer();
        });
    }

    void ScannerService::armScanRequestTimer()
    {
        const std::optional<ScanRequestCollector::Clock::time_point> deadline{ _scanRequests.deadline() };
        if (!deadline)
            return;

        _scanRequestTimer.expires_at(*deadline);
        _scanRequestTimer.async_wait([this](boost::system::error_code ec) {
            if (ec) // cancelled: a newer path moved the deadline and re-armed the timer
                return;

            onScanRequestDue();
        });
    }

    void ScannerService::onScanRequestDue()
    {
        bool scanRunning{};
        {
            const std::shared_lock lock{ _statusMutex };
            scanRunning = _curState == State::InProgress;
        }

        if (scanRunning)
        {
            // Ask the running scan to unwind at its next batch boundary. The steps see the
            // same bool they always did; only the reason tells scan() what to do next.
            _interruptReason = InterruptReason::Pause;
            _abortScan = true;
            return; // scan() picks the request up when it comes back
        }

        runPendingScopedScan();
    }

    void ScannerService::runPendingScopedScan()
    {
        ScanOptions options;
        options.scanDirectories = _scanRequests.take();
        if (options.scanDirectories.empty())
            return;

        scan(options);
    }

    void ScannerService::requestReload()
    {
        abortScan();
        _ioService.post([this]() {
            if (_abortScan)
                return;

            scheduleNextScan();
        });
    }

    ScannerService::Status ScannerService::getStatus() const
    {
        Status res;

        std::shared_lock lock{ _statusMutex };

        res.currentState = _curState;
        res.nextScheduledScan = _nextScheduledScan;
        res.lastCompleteScanStats = _lastCompleteScanStats;
        res.currentScanStepStats = _currentScanStepStats;

        return res;
    }

    void ScannerService::scheduleNextScan()
    {
        LMS_LOG(DBUPDATER, DEBUG, "Scheduling next scan");

        refreshScanSettings();

        // Read straight from the settings row rather than through ScannerSettings: these two
        // say when to scan, not how to read a file, and ScannerSettings is compared field by
        // field to decide whether files need re-reading.
        db::ScanSettings::FullScanPeriod fullScanPeriod{ db::ScanSettings::FullScanPeriod::Never };
        int fullScanDayOfWeek{ 7 };
        {
            auto transaction{ _db.getTLSSession().createReadTransaction() };
            if (const ScanSettings::pointer scanSettings{ ScanSettings::find(_db.getTLSSession(), currentSettingsName) })
            {
                fullScanPeriod = scanSettings->getFullScanPeriod();
                fullScanDayOfWeek = scanSettings->getFullScanDayOfWeek();
            }
        }

        const ScheduledScan next{ computeNextScan(toScanPeriod(_settings.updatePeriod), toScanPeriod(fullScanPeriod), fullScanDayOfWeek, _settings.startTime, Wt::WDateTime::currentDateTime(), _firstSchedule) };

        if (_settings.updatePeriod == ScanSettings::UpdatePeriod::Hourly)
            _firstSchedule = false;
        if (!next.dateTime.isValid())
            LMS_LOG(DBUPDATER, INFO, "Auto scan disabled!");

        if (next.dateTime.isValid())
        {
            ScanOptions scanOptions;
            scanOptions.fullScan = next.fullScan;
            scheduleScan(scanOptions, next.dateTime);
        }

        {
            std::unique_lock lock{ _statusMutex };
            _curState = next.dateTime.isValid() ? State::Scheduled : State::NotScheduled;
            _nextScheduledScan = next.dateTime;
        }

        _events.scanScheduled.emit(_nextScheduledScan);
    }

    void ScannerService::scheduleScan(const ScanOptions& scanOptions, const Wt::WDateTime& dateTime)
    {
        auto cb{ [this, scanOptions](boost::system::error_code ec) {
            if (ec)
                return;

            scan(scanOptions);
        } };

        if (dateTime.isNull())
        {
            LMS_LOG(DBUPDATER, INFO, "Scheduling next scan right now");
            _scheduleTimer.expires_after(std::chrono::seconds{ 0 });
            _scheduleTimer.async_wait(cb);
        }
        else
        {
            std::chrono::system_clock::time_point timePoint{ dateTime.toTimePoint() };
            std::time_t t{ std::chrono::system_clock::to_time_t(timePoint) };
            char ctimeStr[26];

            LMS_LOG(DBUPDATER, INFO, "Scheduling next scan at " << std::string(::ctime_r(&t, ctimeStr)));
            _scheduleTimer.expires_at(timePoint);
            _scheduleTimer.async_wait(cb);
        }
    }

    void ScannerService::scan(const ScanOptions& scanOptions)
    {
        LMS_SCOPED_TRACE_OVERVIEW("Scanner", "Scan");

        _events.scanStarted.emit();

        {
            std::unique_lock lock{ _statusMutex };
            _nextScheduledScan = {};
            _scanRunning = true;
            _scanRunningScoped = scanOptions.isScoped();
        }

        LMS_LOG(UI, INFO, "New scan started!");

        refreshScanSettings();

        ScanContext scanContext;
        std::size_t startIndex{};
        if (!scanOptions.isScoped() && _pausedScan)
        {
            // Resuming the periodic scan that a scoped one interrupted: same context, same
            // stats, and the interrupted step runs again from its own beginning.
            scanContext = std::move(_pausedScan->context);
            startIndex = _pausedScan->stepIndex;
            setPausedScan(std::nullopt);
            LMS_LOG(DBUPDATER, INFO, "Resuming the paused scan at step " << startIndex);
        }
        else
        {
            scanContext.scanOptions = scanOptions;
            scanContext.stats.startTime = Wt::WDateTime::currentDateTime();
        }
        ScanStats& stats{ scanContext.stats };

        const std::size_t stoppedAt{ processScanSteps(scanContext, startIndex) };

        {
            std::unique_lock lock{ _statusMutex };

            _curState = State::NotScheduled;
            _currentScanStepStats.reset(); // must be sync with _curState
            _scanRunning = false;
            _scanRunningScoped = false;
        }

        refreshTracingLoggerStats();
        LMS_LOG(DBUPDATER, INFO, "Scan " << (_abortScan ? "aborted" : "complete") << ". Changes = " << stats.getChangesCount() << " (added = " << stats.additions << ", removed = " << stats.deletions << ", updated = " << stats.updates << ", failures = " << stats.failures << "), Not changed = " << stats.skips << ", Scanned = " << stats.scans << " (errors = " << stats.errorsCount << (stats.errorsCount > 0 ? ": " + formatErrorBreakdown(stats.errorCountsByKind) : std::string{}) << "), features fetched = " << stats.featuresFetched << ",  duplicates = " << stats.duplicates.size());

        {
            auto transaction{ _db.getTLSSession().createReadTransaction() };
            const db::FileStats stats{ _db.getTLSSession().getFileStats() };
            LMS_LOG(DBUPDATER, INFO, stats.getTotalFileCount() << " total files: " << stats.artistInfoCount << " artist info, " << stats.imageCount << " images, " << stats.playListCount << " playlists, " << stats.trackCount << " tracks, " << stats.trackLyricsCount << " lyrics");
        }

        if (_interruptReason == InterruptReason::Pause)
        {
            _interruptReason = InterruptReason::None;
            _abortScan = false;

            // Only a periodic run is worth coming back to: a scoped one is seconds of work and
            // its paths are still in the collector if they were not all read.
            if (!scanOptions.isScoped())
                setPausedScan(PausedScan{ std::move(scanContext), stoppedAt });

            runPendingScopedScan();

            if (_pausedScan)
                scheduleScan(ScanOptions{}); // resume now, not at the next scheduled moment

            return;
        }

        if (!_abortScan)
        {
            stats.stopTime = Wt::WDateTime::currentDateTime();

            // A scoped scan looked at a handful of files, so its numbers say nothing about the
            // library. Publishing them would replace "218431 files, 12 minutes ago" with "3
            // files" on the admin page and in <lastScan>, and the periodic full scan is what
            // that line is meant to describe.
            if (!scanOptions.isScoped())
            {
                std::unique_lock lock{ _statusMutex };
                _lastCompleteScanStats = stats;
            }

            // save current settings as last scan settings to compare during next scans if something changed
            writeScannerSettings(_db.getTLSSession(), lastScanSettingsName, _settings);
            _lastScanSettings = _settings;

            // A library-wide request that arrived during this scoped scan runs now. One that
            // arrived during a library-wide run was absorbed by it and left nothing behind.
            bool runQueuedLibraryScan{};
            {
                const std::unique_lock lock{ _statusMutex };
                runQueuedLibraryScan = scanOptions.isScoped() && _libraryScanQueued;
                _libraryScanQueued = false;
            }

            // A scoped scan is not allowed to move the periodic one: recomputing the moment
            // here is what used to push an hourly scan out by an hour on every request, so
            // the library-wide scan never came round again.
            if (!scanOptions.isScoped())
            {
                LMS_LOG(DBUPDATER, DEBUG, "Scan not aborted, scheduling next scan!");
                scheduleNextScan();
            }
            else if (runQueuedLibraryScan)
            {
                // Takes the schedule timer, as resuming a paused scan does; the library-wide run
                // puts the periodic schedule back when it completes.
                LMS_LOG(DBUPDATER, INFO, "Running the library scan queued during the scoped scan");
                scheduleScan(ScanOptions{});
            }

            _events.scanComplete.emit(stats);
        }
        else
        {
            LMS_LOG(DBUPDATER, DEBUG, "Scan aborted, not scheduling next scan!");
        }
    }

    std::size_t ScannerService::processScanSteps(ScanContext& context, std::size_t startIndex)
    {
        return runScanSteps(
            _scanSteps, context, _abortScan, [this](const ScanStepStats& stats) { notifyInProgress(stats); }, startIndex);
    }

    void ScannerService::refreshScanSettings()
    {
        std::optional<ScannerSettings> newSettings{ readScannerSettings(_db.getTLSSession(), currentSettingsName) };
        assert(newSettings.has_value());
        if (_settings == *newSettings)
            return;

        LMS_LOG(DBUPDATER, DEBUG, "Scanner settings updated");
        LMS_LOG(DBUPDATER, DEBUG, "Using audio scan version " << newSettings->audioScanVersion);
        LMS_LOG(DBUPDATER, DEBUG, "Using artist info scan version " << newSettings->artistInfoScanVersion);

        _settings = std::move(*newSettings);
        if (!_lastScanSettings)
            _lastScanSettings = readScannerSettings(_db.getTLSSession(), lastScanSettingsName);

        auto progressFunc{ [this](const ScanStepStats& stats) {
            notifyInProgressIfNeeded(stats);
        } };

        _fileScanners.clear();
        _fileScanners.add(std::make_unique<ArtistInfoFileScanner>(_db, _settings));
        _fileScanners.add(std::make_unique<AudioFileScanner>(_db, _settings));
        _fileScanners.add(std::make_unique<ImageFileScanner>(_db, _settings));
        _fileScanners.add(std::make_unique<LyricsFileScanner>(_db, _settings));
        _fileScanners.add(std::make_unique<PlayListFileScanner>(_db, _settings));

        _fileScanners.visit([](const IFileScanner& scanner) {
            for (const std::filesystem::path& file : scanner.getSupportedFiles())
                LMS_LOG(DBUPDATER, INFO, scanner.getName() << ": supporting file " << file);

            for (const std::filesystem::path& extension : scanner.getSupportedExtensions())
                LMS_LOG(DBUPDATER, INFO, scanner.getName() << ": supporting file extension " << extension);
        });

        ScanStepBase::InitParams params{
            .jobScheduler = *_jobScheduler,
            .settings = _settings,
            .lastScanSettings = _lastScanSettings.has_value() ? &(_lastScanSettings.value()) : nullptr,
            .progressCallback = progressFunc,
            .abortScan = _abortScan,
            .db = _db,
            .fileScanners = _fileScanners,
            .cachePath = _cachePath
        };

        // Order is important: steps are sequential
        _scanSteps.clear();
        _scanSteps.emplace_back(std::make_unique<ScanStepScanFiles>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepCheckForRemovedFiles>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepArtistReconciliation>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepAssociatePlayListTracks>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepUpdateLibraryFields>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepAssociateReleaseImages>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepAssociateArtistImages>(params)); // must come after ScanStepAssociateReleaseImages (because and artist image can fallback on a release image)
        _scanSteps.emplace_back(std::make_unique<ScanStepAssociateMediumImages>(params)); // must come after ScanStepAssociateReleaseImages (because and medium image can fallback on a release image)
        _scanSteps.emplace_back(std::make_unique<ScanStepAssociateTrackImages>(params));  // must come after ScanStepAssociateMediumImages and ScanStepAssociateReleaseImages (because and track image can fallback on a medium or release image)
        _scanSteps.emplace_back(std::make_unique<ScanStepAssociateExternalLyrics>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepRemoveOrphanedDbEntries>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepCompact>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepOptimize>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepComputeClusterStats>(params));
        _scanSteps.emplace_back(std::make_unique<ScanStepCheckForDuplicatedFiles>(params));
    }

    void ScannerService::notifyInProgress(const ScanStepStats& stepStats)
    {
        {
            std::unique_lock lock{ _statusMutex };

            _curState = State::InProgress;
            _currentScanStepStats = stepStats;
        }

        const auto now{ std::chrono::steady_clock::now() };
        _events.scanInProgress.emit(stepStats);
        _lastScanInProgressEmit = now;
    }

    void ScannerService::notifyInProgressIfNeeded(const ScanStepStats& stepStats)
    {
        const auto now{ std::chrono::steady_clock::now() };

        if (now - _lastScanInProgressEmit >= std::chrono::seconds{ 1 })
            notifyInProgress(stepStats);
    }
} // namespace lms::scanner
