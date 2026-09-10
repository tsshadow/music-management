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

#pragma once

#include "../RequestContext.hpp"
#include "../SubsonicResponse.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace lms::api::subsonic
{
    /**
     * Resolve a list of file paths to playable songs, in the order they were asked for.
     *
     * This is the bridge music-manager's personalized feeds need. It ranks tracks in its own
     * database, where a track has no LMS id -- the two id spaces are unrelated -- and the file
     * path is the only name both sides know. A client asks music-manager what belongs in the
     * feed and asks this what to play.
     *
     * Deliberately dumb: no ranking, no filtering, and no call back out to music-manager. A
     * Subsonic request that waits on an HTTP round trip holds a Wt thread while it waits, and
     * that pool is small enough that a slow music-manager once took the whole site down.
     *
     * A path this server does not have is left out of the answer instead of failing it. The
     * two libraries are allowed to differ, and a feed one track shorter beats a car that gets
     * an error instead of music.
     */
    Response handleGetSongsByPath(RequestContext& context);

    namespace songsByPath
    {
        /**
         * Every spelling of `path` worth looking up here, best first.
         *
         * Paths are library-relative, the same rule `resolveScanScope` states and for the same
         * reason: music-manager mounts the library at /mnt/music while this server sees it at
         * /music, so its absolute path names a file this server does not have. An absolute path
         * is still accepted and used as given -- a caller that already speaks this server's
         * spelling must never be answered with a re-rooted guess.
         *
         * With several media libraries a relative path is tried under each, in configuration
         * order, rather than refused the way a scan scope is. The first root holding a matching
         * path wins, and that is a real ambiguity rather than a harmless one: if two libraries
         * both hold `Album/01.mp3` and they are different recordings, the caller gets whichever
         * library is configured first, with nothing in the answer to say so. It is accepted
         * because a deployment with overlapping relative paths does not exist here -- there is
         * one media library -- and refusing an ambiguous path outright would turn a second
         * library into a feed that silently stops resolving. Anything that adds a second
         * library has to revisit this.
         */
        std::vector<std::filesystem::path> candidateSpellings(
            const std::filesystem::path& path,
            const std::vector<std::filesystem::path>& roots);
    } // namespace songsByPath
} // namespace lms::api::subsonic
