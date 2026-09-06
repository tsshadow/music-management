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
#include <fstream>

#include <gtest/gtest.h>

#include "SubsonicResponse.hpp"
#include "endpoints/ScanScope.hpp"

namespace lms::api::subsonic::tests
{
    namespace
    {
        const std::vector<std::filesystem::path> oneRoot{ "/music" };
        const std::vector<std::filesystem::path> twoRoots{ "/music", "/podcasts" };
    } // namespace

    TEST(ScanScope, aRelativePathIsResolvedAgainstTheSingleRoot)
    {
        // MuMa mounts the library at /mnt/music and this server sees it at /music, so an
        // absolute path from the client would name a directory that does not exist here.
        EXPECT_EQ(resolveScanScope("EPs/Evolve AU", oneRoot), "/music/EPs/Evolve AU");
    }

    TEST(ScanScope, anAbsolutePathInsideARootIsAccepted)
    {
        EXPECT_EQ(resolveScanScope("/music/EPs/Evolve AU", oneRoot), "/music/EPs/Evolve AU");
    }

    TEST(ScanScope, traversalIsClosedByNormalisation)
    {
        EXPECT_THROW(resolveScanScope("/music/../etc", oneRoot), BadParameterGenericError);
        EXPECT_THROW(resolveScanScope("../etc", oneRoot), BadParameterGenericError);
    }

    TEST(ScanScope, aPathOutsideEveryRootIsRefusedRatherThanWidened)
    {
        // A client that asked for one folder and silently got the whole library back would
        // start an hour of work every time it tried.
        EXPECT_THROW(resolveScanScope("/etc", oneRoot), BadParameterGenericError);
    }

    TEST(ScanScope, aRelativePathIsAmbiguousWithSeveralRoots)
    {
        EXPECT_THROW(resolveScanScope("EPs", twoRoots), BadParameterGenericError);
        EXPECT_EQ(resolveScanScope("/podcasts/show", twoRoots), "/podcasts/show");
    }

    TEST(ScanScope, aTrailingSeparatorIsHarmless)
    {
        EXPECT_EQ(resolveScanScope("/music/EPs/", oneRoot), "/music/EPs");
    }

    TEST(ScanScope, aPathThatNoLongerExistsIsStillValid)
    {
        // The more important half of the feature: this is how the rows under a folder that
        // was moved away get removed. A path that is not there is accepted without a word.
        EXPECT_EQ(resolveScanScope("/music/gone-4f1c", oneRoot), "/music/gone-4f1c");
    }

    TEST(ScanScope, anExistingFileIsRefused)
    {
        // The scan step runs a directory_iterator over what it gets, so a file would scan
        // nothing at all and look like a working request. Only checkable when the path is
        // there -- and when it is not, the test above is the case that matters.
        const std::filesystem::path tempRoot{ std::filesystem::temp_directory_path() / "lms-scan-scope-test" };
        std::filesystem::create_directories(tempRoot / "folder");
        std::ofstream{ tempRoot / "folder" / "track.mp3" } << "x";

        const std::vector<std::filesystem::path> roots{ tempRoot };
        EXPECT_EQ(resolveScanScope((tempRoot / "folder").string(), roots), tempRoot / "folder");
        EXPECT_THROW(resolveScanScope((tempRoot / "folder" / "track.mp3").string(), roots), BadParameterGenericError);

        std::filesystem::remove_all(tempRoot);
    }
} // namespace lms::api::subsonic::tests
