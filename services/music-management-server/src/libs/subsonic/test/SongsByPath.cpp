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

#include <filesystem>
#include <vector>

#include <gtest/gtest.h>

#include "endpoints/SongsByPath.hpp"

namespace lms::api::subsonic::tests
{
    namespace
    {
        const std::vector<std::filesystem::path> oneLibrary{ "/music" };
        const std::vector<std::filesystem::path> twoLibraries{ "/music", "/podcasts" };

        using songsByPath::candidateSpellings;
    } // namespace

    TEST(SongsByPath, aRelativePathIsResolvedAgainstTheRoot)
    {
        // What music-manager sends: it knows the file as /mnt/music/EPs/..., which is a path
        // this server does not have, so the feed hands over the library-relative part.
        const std::vector<std::filesystem::path> expected{ "/music/EPs/Evolve AU/01.mp3" };
        EXPECT_EQ(candidateSpellings("EPs/Evolve AU/01.mp3", oneLibrary), expected);
    }

    TEST(SongsByPath, everyRootIsTriedForARelativePath)
    {
        // Unlike a scan scope, an ambiguous relative path is not refused here. Configuration
        // order decides, and with two libraries that both hold the same relative path that is a
        // real ambiguity -- see the note in the header. This pins the order so the choice is at
        // least the same on every call.
        const std::vector<std::filesystem::path> expected{ "/music/x/01.mp3", "/podcasts/x/01.mp3" };
        EXPECT_EQ(candidateSpellings("x/01.mp3", twoLibraries), expected);
    }

    TEST(SongsByPath, anAbsolutePathIsUsedAsGiven)
    {
        // A caller that already speaks this server's spelling is answered with it, never with
        // a re-rooted guess that could name a different file with the same name.
        const std::vector<std::filesystem::path> expected{ "/music/EPs/x/01.mp3" };
        EXPECT_EQ(candidateSpellings("/music/EPs/x/01.mp3", oneLibrary), expected);
    }

    TEST(SongsByPath, anAbsolutePathOutsideEveryRootIsStillOnlyItself)
    {
        // It resolves to nothing, and that is the point: this endpoint looks a path up in the
        // database, it never opens it, so an unknown path costs one missed lookup.
        const std::vector<std::filesystem::path> expected{ "/etc/passwd" };
        EXPECT_EQ(candidateSpellings("/etc/passwd", oneLibrary), expected);
    }

    TEST(SongsByPath, traversalIsCollapsedRatherThanRefused)
    {
        const std::vector<std::filesystem::path> expected{ "/music/01.mp3" };
        EXPECT_EQ(candidateSpellings("EPs/../01.mp3", oneLibrary), expected);
    }

    TEST(SongsByPath, aPathWithoutAFilenameYieldsNothing)
    {
        // A directory is not a song. Answering with the directory would make the lookup
        // meaningless rather than empty.
        EXPECT_TRUE(candidateSpellings("EPs/Evolve AU/", oneLibrary).empty());
        EXPECT_TRUE(candidateSpellings("", oneLibrary).empty());
    }

    TEST(SongsByPath, aDuplicateRootIsOnlyTriedOnce)
    {
        const std::vector<std::filesystem::path> repeated{ "/music", "/music" };
        const std::vector<std::filesystem::path> expected{ "/music/01.mp3" };
        EXPECT_EQ(candidateSpellings("01.mp3", repeated), expected);
    }
} // namespace lms::api::subsonic::tests
