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

#include "ScanStepCheckForRemovedFiles.hpp"

#include <deque>
#include <filesystem>
#include <span>
#include <vector>

#include "core/IJob.hpp"
#include "core/ILogger.hpp"
#include "core/Path.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/ArtistInfo.hpp"
#include "database/objects/Image.hpp"
#include "database/objects/PlayListFile.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackLyrics.hpp"

#include "BatchedRemoval.hpp"
#include "FileScanners.hpp"
#include "JobQueue.hpp"
#include "ScanContext.hpp"
#include "ScanErrorPolicy.hpp"
#include "ScannerSettings.hpp"
#include "services/scanner/ScannerStats.hpp"

namespace lms::scanner
{
    namespace
    {
        template<typename IdType>
        struct FileToCheck
        {
            IdType objectId;
            std::filesystem::path file;

            FileToCheck(IdType _objectId, const std::filesystem::path& _file)
                : objectId{ _objectId }, file{ _file } {}
        };

        template<typename IdType>
        class CheckForRemovedFilesJob : public core::IJob
        {
        public:
            CheckForRemovedFilesJob(const ScannerSettings& settings, const FileScanners& scanners, std::span<const FileToCheck<IdType>> filesToCheck)
                : _settings{ settings }
                , _scanners{ scanners }
                , _filesToCheck{ std::cbegin(filesToCheck), std::cend(filesToCheck) }
            {
            }

            CheckForRemovedFilesJob(const CheckForRemovedFilesJob&) = delete;
            CheckForRemovedFilesJob& operator=(const CheckForRemovedFilesJob&) = delete;

            std::size_t getProcessedCount() const { return _processedCount; }
            std::span<const IdType> getObjectsToRemove() const { return _objectsToRemove; }

        private:
            core::LiteralString getName() const override { return "Check For Removed Files"; }
            void run() override
            {
                for (const FileToCheck<IdType>& fileToCheck : _filesToCheck)
                {
                    if (!checkFile(fileToCheck.file))
                        _objectsToRemove.push_back(fileToCheck.objectId);
                }

                _processedCount += _filesToCheck.size();
            }

            bool checkFile(const std::filesystem::path& p)
            {
                std::error_code ec;
                const std::filesystem::directory_entry fileEntry{ p, ec };
                if (ec)
                {
                    // A file that is simply gone is what this step exists to find: the importer
                    // moves releases out of the queue and artwork gets replaced all day. That
                    // outcome was logged as an ERROR, about 92,000 lines in six hours on
                    // production, burying the errors that are real (bug report 121).
                    if (isMissingFileError(ec))
                        LMS_LOG(DBUPDATER, DEBUG, "Removing " << p << ": missing");
                    else
                        LMS_LOG(DBUPDATER, ERROR, "Error while checking file " << p << ": " << ec.message());
                    return false;
                }

                // For file, make sure the the file still exists, is a regular file, is in a media directory and is of a supported format
                if (!fileEntry.exists() || !fileEntry.is_regular_file())
                {
                    LMS_LOG(DBUPDATER, DEBUG, "Removing " << p << ": missing");
                    return false;
                }

                if (std::none_of(std::cbegin(_settings.mediaLibraries), std::cend(_settings.mediaLibraries),
                                 [&](const MediaLibraryInfo& libraryInfo) {
                                     return core::pathUtils::isPathInRootPath(p, libraryInfo.rootDirectory, &excludeDirFileName);
                                 }))
                {
                    LMS_LOG(DBUPDATER, DEBUG, "Removing " << p << ": out of media directory");
                    return false;
                }

                if (!_scanners.select(p))
                {
                    LMS_LOG(DBUPDATER, DEBUG, "Removing " << p << ": file format no longer handled");
                    return false;
                }

                return true;
            }

            const ScannerSettings& _settings;
            const FileScanners& _scanners;
            std::vector<FileToCheck<IdType>> _filesToCheck;
            std::vector<IdType> _objectsToRemove;
            std::size_t _processedCount{};
        };

        // `directory` empty means the whole table, which is what a normal scan asks for.
        //
        // `cachepath` and `directory` are both paths and were adjacent, so the call that means
        // "skip the cache, look under this scope" compiled just as happily with the two the
        // other way round -- and would then have skipped the scope and scanned the cache.
        template<typename Object>
        bool fetchNextFilesToCheck(db::Session& session, const std::filesystem::path& cachepath, typename Object::IdType& lastCheckedId, const std::filesystem::path& directory, std::vector<FileToCheck<typename Object::IdType>>& filesToCheck)
        {
            constexpr std::size_t batchSize{ 200 };

            filesToCheck.clear();
            filesToCheck.reserve(batchSize);

            auto transaction{ session.createReadTransaction() };

            while (filesToCheck.size() < batchSize)
            {
                const typename Object::IdType previousLastCheckedId{ lastCheckedId };
                auto onFile{ [&](Object::IdType objectId, const std::filesystem::path& filePath) {
                    // Do not consider files in the cache directory as they are not managed by the scanner itself
                    if (core::pathUtils::isPathInRootPath(filePath, cachepath))
                        return;

                    // special case for track lyrics, only check external lyrics
                    if constexpr (std::is_same_v<Object, db::TrackLyrics>)
                    {
                        if (filePath.empty())
                            return;
                    }

                    filesToCheck.emplace_back(objectId, filePath);
                } };

                if (directory.empty())
                    Object::findAbsoluteFilePath(session, lastCheckedId, batchSize, onFile);
                else
                    Object::findAbsoluteFilePathInDirectory(session, lastCheckedId, batchSize, directory, onFile);

                if (previousLastCheckedId == lastCheckedId)
                    break;
            }

            return !filesToCheck.empty();
        }
    } // namespace

    bool ScanStepCheckForRemovedFiles::needProcess([[maybe_unused]] const ScanContext& context) const
    {
        // always check for removed files
        return true;
    }

    void ScanStepCheckForRemovedFiles::process(ScanContext& context)
    {
        db::Session& session{ _db.getTLSSession() };

        if (context.scanOptions.isScoped())
        {
            // Not known up front: the count would mean "every file in the library" while this
            // run only looks under the requested subtrees, and the progress bar would sit at
            // 0%. ScanStepStats::progress() already guards against a zero total.
            context.currentStepStats.totalElems = 0;
            LMS_LOG(DBUPDATER, DEBUG, "Checking for removed files under " << context.scanOptions.scanDirectories.size() << " scan scope(s)...");
        }
        else
        {
            {
                auto transaction{ session.createReadTransaction() };
                context.currentStepStats.totalElems = session.getFileStats().getTotalFileCount();
            }
            LMS_LOG(DBUPDATER, DEBUG, context.currentStepStats.totalElems << " files to be checked...");
        }

        checkForRemovedFiles<db::Track>(context);
        checkForRemovedFiles<db::Image>(context);
        checkForRemovedFiles<db::TrackLyrics>(context);
        checkForRemovedFiles<db::PlayListFile>(context);
        checkForRemovedFiles<db::ArtistInfo>(context);
    }

    template<typename Object>
    void ScanStepCheckForRemovedFiles::checkForRemovedFiles(ScanContext& context)
    {
        using ObjectIdType = typename Object::IdType;

        if (_abortScan)
            return;

        db::Session& session{ _db.getTLSSession() };

        std::deque<ObjectIdType> objectIdsToRemove;

        // Only collects: the removal happens below, one write batch at a time, so that
        // finishing the queue for a priority pass costs the file checks in flight and not the
        // writes they lead to (bug report 136).
        auto processJobsDone = [&](std::span<std::unique_ptr<core::IJob>> jobs) {
            if (_abortScan)
                return;

            for (const auto& job : jobs)
            {
                const auto& checkJob{ static_cast<const CheckForRemovedFilesJob<ObjectIdType>&>(*job) };
                std::span<const ObjectIdType> objectsToRemove{ checkJob.getObjectsToRemove() };

                objectIdsToRemove.insert(std::end(objectIdsToRemove), std::cbegin(objectsToRemove), std::cend(objectsToRemove));

                context.currentStepStats.processedElems += checkJob.getProcessedCount();
            }

            _progressCallback(context.currentStepStats);
        };

        JobQueue queue{ getJobScheduler(), 50, processJobsDone, 1, 0.85F };

        // Second filesystem-bound step of a library-wide scan, and the second place announced
        // folders are let through (bug report 126). The pass needs the job scheduler to itself,
        // so what is in flight is finished first. The keyset walk resumes from lastCheckedId,
        // so rows the pass adds or removes are simply met, or not, further on; an id the pass
        // already removed and that is still pending here is deleted a second time, which is a
        // no-op.
        const auto letPriorityWorkThrough{ [&] {
            if (!isPriorityWorkDue())
                return;

            queue.finish();
            runPriorityWork();
        } };

        const auto removePending{ [&](bool fullBatchesOnly) {
            constexpr std::size_t writeBatchSize{ 50 };
            context.stats.deletions += removeInWriteBatches(
                objectIdsToRemove, writeBatchSize, fullBatchesOnly,
                [&](std::span<const ObjectIdType> ids) {
                    auto transaction{ session.createWriteTransaction() };
                    session.destroy<Object>(ids);
                },
                // Between two write batches, with no transaction open: the removal of thousands
                // of rows no longer holds a priority pass back until it is all done.
                letPriorityWorkThrough);
        } };

        std::vector<FileToCheck<ObjectIdType>> filesToCheck;

        // One keyset walk per scope rather than a dynamic multi-prefix OR: a scoped scan
        // carries two paths per moved release, and hand-built SQL in five call sites would
        // buy nothing measurable at this size.
        std::vector<std::filesystem::path> scopes{ context.scanOptions.scanDirectories };
        if (scopes.empty())
            scopes.emplace_back(); // the whole table

        for (const std::filesystem::path& scope : scopes)
        {
            ObjectIdType lastCheckedId;
            while (fetchNextFilesToCheck<Object>(session, getCachePath(), lastCheckedId, scope, filesToCheck))
            {
                queue.push(std::make_unique<CheckForRemovedFilesJob<ObjectIdType>>(_settings, getFileScanners(), filesToCheck));

                letPriorityWorkThrough();
                if (!_abortScan)
                    removePending(true /* full batches only */);
            }
        }

        // process all remaining objects
        queue.finish();
        removePending(false /* full batches only */);
    }
} // namespace lms::scanner
