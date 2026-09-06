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

#include <gtest/gtest.h>

#include "services/scanner/ScannerOptions.hpp"

namespace lms::scanner::tests
{
    TEST(ScanOptions, isNotScopedByDefault)
    {
        EXPECT_FALSE(ScanOptions{}.isScoped());
    }

    TEST(ScanOptions, isScopedOnceADirectoryIsSet)
    {
        ScanOptions options;
        options.scanDirectories.emplace_back("/music/EPs/Evolve AU");

        EXPECT_TRUE(options.isScoped());
    }

    TEST(ScanOptions, survivesACopy)
    {
        // requestImmediateScan hands the options to a timer lambda by value and scan() copies
        // them into the ScanContext, so a scope that did not survive a copy would silently
        // become a full library scan.
        ScanOptions options;
        options.fullScan = true;
        options.scanDirectories.emplace_back("/music/EPs/Evolve AU");
        options.scanDirectories.emplace_back("/music/EPs/__TODO/EVAU021E");

        const ScanOptions copy{ options };
        ScanOptions assigned;
        assigned = options;

        EXPECT_TRUE(copy.isScoped());
        EXPECT_TRUE(assigned.isScoped());
        EXPECT_EQ(copy.scanDirectories.size(), 2);
        EXPECT_EQ(assigned.scanDirectories.back(), "/music/EPs/__TODO/EVAU021E");
        EXPECT_TRUE(assigned.fullScan);
    }

    TEST(ScanOptions, aScopeAndAFullScanAreNotExclusive)
    {
        // "re-read every file under this folder whether or not its mtime moved" is the scoped
        // force scan, and nothing in the options is allowed to make those two contradict.
        ScanOptions options;
        options.fullScan = true;
        options.scanDirectories.emplace_back("/music/EPs/Evolve AU");

        EXPECT_TRUE(options.isScoped());
        EXPECT_TRUE(options.fullScan);
    }
} // namespace lms::scanner::tests
