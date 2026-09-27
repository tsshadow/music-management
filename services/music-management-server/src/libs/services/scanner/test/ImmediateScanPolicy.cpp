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

#include "ImmediateScanPolicy.hpp"

namespace lms::scanner::tests
{
    namespace
    {
        constexpr RunningScan idle{};
        constexpr RunningScan libraryScanRunning{ .inProgress = true, .scoped = false };
        constexpr RunningScan scopedScanRunning{ .inProgress = true, .scoped = true };
    } // namespace

    TEST(ImmediateScanPolicy, startsWhenNothingRuns)
    {
        EXPECT_EQ(decideImmediateScan(ScanOptions{}, idle), ImmediateScanDecision::Start);
    }

    // The tagger's trigger used to abort the running library-wide scan every five minutes, and
    // wait for it to unwind on the HTTP thread; a scan that takes most of an hour never finished.
    TEST(ImmediateScanPolicy, aPlainRequestJoinsARunningLibraryScan)
    {
        EXPECT_EQ(decideImmediateScan(ScanOptions{}, libraryScanRunning), ImmediateScanDecision::Absorb);
    }

    // Bug report 126: announced folders are read in a priority pass inside the running
    // library-wide scan, which stays the scan that runs (scoped = false). A plain request in that
    // moment joins it, as at any other moment -- it neither aborts the scan nor queues a second one.
    TEST(ImmediateScanPolicy, aPlainRequestDuringAPriorityPassJoinsTheLibraryScan)
    {
        constexpr RunningScan libraryScanInAPriorityPass{ .inProgress = true, .scoped = false };
        EXPECT_EQ(decideImmediateScan(ScanOptions{}, libraryScanInAPriorityPass), ImmediateScanDecision::Absorb);
    }

    // What a folder announcement looks like when it reaches the immediate-scan path by mistake:
    // it is not a plain library-wide request, so the policy never absorbs it.
    TEST(ImmediateScanPolicy, aScopedRequestIsNeverAbsorbed)
    {
        ScanOptions scoped;
        scoped.scanDirectories.emplace_back("/music/Soundcloud/2TD");
        EXPECT_EQ(decideImmediateScan(scoped, libraryScanRunning), ImmediateScanDecision::Start);
    }

    // A scoped scan reads a few folders; the library-wide request still has to run, after it.
    TEST(ImmediateScanPolicy, aPlainRequestWaitsForARunningScopedScan)
    {
        EXPECT_EQ(decideImmediateScan(ScanOptions{}, scopedScanRunning), ImmediateScanDecision::QueueAfterCurrent);
    }

    // An admin asking for a full re-read, an optimize or a compact asks for something the running
    // scan will not do: that still starts over, as it always did.
    TEST(ImmediateScanPolicy, aRequestForMoreThanTheRunningScanDoesStillStartsOver)
    {
        ScanOptions fullScan;
        fullScan.fullScan = true;
        ScanOptions forceOptimize;
        forceOptimize.forceOptimize = true;
        ScanOptions compact;
        compact.compact = true;

        for (const ScanOptions& request : { fullScan, forceOptimize, compact })
        {
            EXPECT_EQ(decideImmediateScan(request, libraryScanRunning), ImmediateScanDecision::Start);
            EXPECT_EQ(decideImmediateScan(request, scopedScanRunning), ImmediateScanDecision::Start);
        }
    }
} // namespace lms::scanner::tests
