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

#include "ScanScope.hpp"

#include <algorithm>
#include <system_error>

#include "core/Path.hpp"

#include "SubsonicResponse.hpp"

namespace lms::api::subsonic
{
    std::filesystem::path resolveScanScope(const std::string& rawPath, const std::vector<std::filesystem::path>& roots)
    {
        std::filesystem::path path{ rawPath };

        if (!path.is_absolute())
        {
            if (roots.size() != 1)
                throw BadParameterGenericError{ "path", "relative path is ambiguous with several media libraries" };
            path = roots.front() / path;
        }

        // lexically_normal, never canonical: canonical throws for a path that no longer
        // exists, and a vanished directory is the case this endpoint exists to serve. It also
        // collapses "..", so traversal is closed here rather than by a string test, and it
        // matches how the library roots themselves are normalised.
        path = path.lexically_normal();

        // "/music/EPs/" and "/music/EPs" must mean the same scope; lexically_normal keeps the
        // trailing separator, and the removed-file query derives its byte range from this path.
        if (!path.has_filename())
            path = path.parent_path();

        const bool inSomeRoot{ std::any_of(std::cbegin(roots), std::cend(roots),
                                           [&](const std::filesystem::path& root) { return core::pathUtils::isPathInRootPath(path, root); }) };
        if (!inSomeRoot)
            throw BadParameterGenericError{ "path", "not inside a media library" };

        // A scoped scan walks what it is given with a directory_iterator, so a file would scan
        // nothing while looking like it worked. Written this way round on purpose: is_directory
        // on a path that does not exist is false, and a vanished path must stay valid.
        std::error_code ec;
        if (std::filesystem::exists(path, ec) && !std::filesystem::is_directory(path, ec))
            throw BadParameterGenericError{ "path", "not a directory" };

        return path;
    }
} // namespace lms::api::subsonic
