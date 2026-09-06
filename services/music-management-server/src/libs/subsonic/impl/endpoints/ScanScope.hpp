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
#include <vector>

namespace lms::api::subsonic
{
    // Resolves one caller-supplied scan scope against the configured media library roots.
    //
    // Paths are library-relative by default and that is not a convenience: MuMa mounts the
    // library at /mnt/music while LMS sees it at /music, so an absolute path from the client
    // would name a directory this server does not have. An absolute path is still accepted,
    // for an operator poking the endpoint from the LMS host itself.
    //
    // Throws BadParameterGenericError for a path outside every root, for a relative path when
    // there is more than one root, and for an existing entry that is not a directory. A path
    // that no longer exists is valid: that is how the rows under a folder that was moved away
    // get removed.
    std::filesystem::path resolveScanScope(const std::string& rawPath, const std::vector<std::filesystem::path>& roots);
} // namespace lms::api::subsonic
