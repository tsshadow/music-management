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

#include <filesystem>
#include <string>
#include <string_view>
#include <system_error>

#include "services/scanner/ScanErrors.hpp"
#include "services/scanner/ScannerOptions.hpp"
#include "services/scanner/ScannerStats.hpp"

namespace lms::scanner
{
    // MuMa's import queue: releases land here, get extracted, retagged and renamed, and are then
    // moved into the library. Tracks inside it are playable on purpose, so the folder is not
    // excluded from scanning; only what a half-processed release says about itself is ignored.
    static inline const std::filesystem::path importQueueDirName{ "__TODO" };

    // Which concrete ScanError this is.
    ScanErrorKind getScanErrorKind(const ScanError& error);

    // Short, stable label for a kind, as it appears in the scan summary log line.
    std::string_view toString(ScanErrorKind kind);

    // "637 playlist-all-entries-missing, 330 playlist-entry-missing", largest first, kinds with
    // no errors left out. Empty when there were no errors at all.
    std::string formatErrorBreakdown(const ScanErrorCounts& counts);

    // Whether the problems found while matching a playlist's entries to tracks are reported.
    enum class PlayListErrorDecision
    {
        Report,
        // The playlist lies outside the folders a scoped scan was asked to look at. The
        // association step still walks every playlist in the library, so without this each
        // scoped scan re-reported the same several hundred stale playlists (bug report 121).
        // The library-wide scan reports them, and that is the one whose errors are published.
        SkipOutOfScope,
        // The playlist lies in the import queue, where a release's own .m3u names the files as
        // they were before the tagger renamed them, or the folder is already gone.
        SkipImportQueue,
    };
    PlayListErrorDecision decidePlayListErrorReporting(const std::filesystem::path& playListFile, const ScanOptions& options);

    // True when checking a file failed only because it is not there any more: that is the
    // normal "removed" outcome of the removed-files check, not an error worth an ERROR line.
    bool isMissingFileError(std::error_code ec);
} // namespace lms::scanner
