/*
 * copyright (c) 2026 emeric poupon
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

#include "SongsByPath.hpp"

#include "../ParameterParsing.hpp"
#include "database/Session.hpp"
#include "database/objects/MediaLibrary.hpp"
#include "database/objects/Track.hpp"
#include "responses/Song.hpp"

#include <algorithm>
#include <string>

namespace lms::api::subsonic
{
    namespace
    {
        // A feed is thirty tracks and the biggest one anybody has proposed is a hundred. The
        // point of the ceiling is that every path costs a handful of indexed lookups, so an
        // unbounded list would let one request walk the whole library from a phone.
        constexpr std::size_t maxPathCount{ 100 };
    } // namespace

    namespace songsByPath
    {
        std::vector<std::filesystem::path> candidateSpellings(
            const std::filesystem::path& path,
            const std::vector<std::filesystem::path>& roots)
        {
            std::vector<std::filesystem::path> candidates;

            const auto add{ [&](const std::filesystem::path& candidate) {
                if (candidate.empty() || !candidate.has_filename())
                    return;
                if (std::find(candidates.begin(), candidates.end(), candidate) == candidates.end())
                    candidates.push_back(candidate);
            } };

            if (path.is_absolute())
            {
                // lexically_normal closes traversal here rather than by a string test, the same
                // way resolveScanScope does, and matches how the roots themselves are normalised.
                add(path.lexically_normal());
                return candidates;
            }

            for (const std::filesystem::path& root : roots)
                add((root / path).lexically_normal());

            return candidates;
        }
    } // namespace songsByPath

    Response handleGetSongsByPath(RequestContext& context)
    {
        const std::vector<std::string> paths{ getMandatoryMultiParametersAs<std::string>(context.getParameters(), "path") };
        if (paths.size() > maxPathCount)
            throw ParameterValueTooHighGenericError{ "path", maxPathCount };

        auto transaction{ context.getDbSession().createReadTransaction() };

        std::vector<std::filesystem::path> roots;
        db::MediaLibrary::find(context.getDbSession(), [&](const db::MediaLibrary::pointer& library) {
            roots.push_back(library->getPath());
        });

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& songsNode{ response.createNode("songsByPath") };

        for (const std::string& path : paths)
        {
            db::Track::pointer track;
            for (const std::filesystem::path& spelling : songsByPath::candidateSpellings(path, roots))
            {
                track = db::Track::findByPath(context.getDbSession(), spelling);
                if (track)
                    break;
            }

            // A path this server does not have is left out rather than refused. The two
            // libraries are allowed to differ, and a feed that is one track shorter is a far
            // better answer than a car that gets an error instead of music.
            if (track)
                songsNode.addArrayChild("song", createSongNode(context, track, true));
        }

        return response;
    }
} // namespace lms::api::subsonic
