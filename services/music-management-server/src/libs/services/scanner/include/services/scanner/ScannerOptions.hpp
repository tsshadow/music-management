/*
 * Copyright (C) 2024 Emeric Poupon
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
#include <vector>

namespace lms::scanner
{
    struct ScanOptions
    {
        bool fullScan{};      // scan files even if not changed
        bool forceOptimize{}; // force optimize database
        bool compact{};       // compact the database

        // When non-empty, only these directory subtrees are scanned instead of every media
        // library. MuMa moves and retags files continuously and used to have no way to say
        // so; the library-wide incremental scan takes the better part of an hour here, so a
        // change waited up to two hours before it showed up.
        //
        // Each entry is absolute, lexically normal, and inside a media library root -- all
        // three are established at the API boundary, never here. A directory that no longer
        // exists is valid and is the more important half of the feature: it is how the rows
        // underneath a folder that was moved away get removed.
        //
        // Combines with fullScan, which then means "re-read every file under these paths
        // whether or not its mtime moved".
        std::vector<std::filesystem::path> scanDirectories;

        bool isScoped() const { return !scanDirectories.empty(); }
    };
} // namespace lms::scanner
