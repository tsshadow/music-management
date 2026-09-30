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

#include <atomic>
#include <chrono>
#include <memory>
#include <thread>
#include <vector>

#include <gtest/gtest.h>

#include <Wt/Dbo/backend/Sqlite3.h>

#include "database/GuardedWrite.hpp"
#include "database/WritePacer.hpp"

#include "Common.hpp"

// Bug report 134: the scanner kept the lms.db write lock to itself for as long as it had
// something to write. Bug report 135: background writes that must not throw.
namespace lms::db::tests
{
    namespace
    {
        using namespace std::chrono_literals;

        // A clock that only moves when told to, and a sleep that moves it.
        struct FakeTime
        {
            WritePacer::Clock::time_point now{ WritePacer::Clock::time_point{} + 1h };
            std::vector<WritePacer::Clock::duration> sleeps;

            WritePacer makePacer(WritePacer::Settings settings = { .maxStretch = 500ms, .pause = 120ms })
            {
                return WritePacer{
                    settings,
                    [this] { return now; },
                    [this](WritePacer::Clock::duration duration) {
                        sleeps.push_back(duration);
                        now += duration;
                    },
                };
            }
        };

        // One write transaction as the pacer sees it: `hold` with the lock, then `gap` without.
        void simulateWrite(FakeTime& time, WritePacer& pacer, WritePacer::Clock::duration hold, WritePacer::Clock::duration gap)
        {
            pacer.onWriteBegin();
            time.now += hold;
            pacer.onWriteEnd();
            time.now += gap;
        }

        ClusterId createPacingTestCluster(Session& session)
        {
            auto transaction{ session.createWriteTransaction() };
            const ClusterType::pointer type{ session.create<ClusterType>("Genre") };
            return session.create<Cluster>(type, "Hardstyle")->getId();
        }

        // Stands in for the scanner: back-to-back short write transactions for `duration`, each
        // holding the lock for `hold`, with nothing in between -- the shape that starved every
        // other writer on production.
        void runBulkWriter(IDb& db, ClusterId clusterId, std::unique_ptr<WritePacer> pacer, std::chrono::milliseconds duration, std::chrono::milliseconds hold, std::atomic<bool>& started)
        {
            Session session{ db };
            session.setWritePacer(std::move(pacer));

            const auto end{ std::chrono::steady_clock::now() + duration };
            std::size_t count{};
            while (std::chrono::steady_clock::now() < end)
            {
                auto transaction{ session.createWriteTransaction() };
                Cluster::find(session, clusterId).modify()->setTrackCount(++count);
                std::this_thread::sleep_for(hold);
                started = true;
            }
        }
    } // namespace

    TEST(WritePacer, doesNotPauseAStretchShorterThanTheLimit)
    {
        FakeTime time;
        WritePacer pacer{ time.makePacer() };

        for (int i{}; i < 9; ++i)
            simulateWrite(time, pacer, 50ms, 1ms); // 459 ms of back-to-back writing

        EXPECT_TRUE(time.sleeps.empty());
        EXPECT_EQ(pacer.getPauseCount(), 0);
    }

    TEST(WritePacer, pausesOnceTheStretchReachesTheLimit)
    {
        FakeTime time;
        WritePacer pacer{ time.makePacer() };

        for (int i{}; i < 11; ++i)
            simulateWrite(time, pacer, 50ms, 1ms); // the 11th begins 510 ms into the stretch

        ASSERT_EQ(time.sleeps.size(), 1);
        EXPECT_EQ(time.sleeps.front(), 120ms);
        EXPECT_EQ(pacer.getPauseCount(), 1);
        EXPECT_EQ(pacer.getTotalPause(), 120ms);
    }

    TEST(WritePacer, keepsPausingForAsLongAsTheWritingGoesOn)
    {
        FakeTime time;
        WritePacer pacer{ time.makePacer() };

        // 5 s of writing: one pause after each ~0.5 s stretch.
        for (int i{}; i < 100; ++i)
            simulateWrite(time, pacer, 49ms, 1ms);

        EXPECT_GE(pacer.getPauseCount(), 8);
        EXPECT_LE(pacer.getPauseCount(), 10);
    }

    TEST(WritePacer, aLongEnoughGapCountsAsABreak)
    {
        FakeTime time;
        WritePacer pacer{ time.makePacer() };

        // Each write is followed by a gap as long as a pause: other writers had their turn.
        for (int i{}; i < 20; ++i)
            simulateWrite(time, pacer, 100ms, 120ms);

        EXPECT_TRUE(time.sleeps.empty());
    }

    TEST(WritePacer, doesNotPaceANestedWriteTransaction)
    {
        FakeTime time;
        WritePacer pacer{ time.makePacer() };

        pacer.onWriteBegin();
        time.now += 2s; // a long outer transaction
        pacer.onWriteBegin();
        pacer.onWriteEnd();
        pacer.onWriteEnd();

        EXPECT_TRUE(time.sleeps.empty());

        // The outer transaction is what counts: it held the lock for 2 s, so the next write that
        // follows without a break waits first.
        pacer.onWriteBegin();
        pacer.onWriteEnd();
        EXPECT_EQ(time.sleeps.size(), 1);
    }

    // The production symptom: music-manager's connection could not get the lock while the scanner
    // wrote in short transactions without a break. With a pacer, a connection waiting on SQLite's
    // busy handler gets in within about one stretch.
    TEST(WritePacer, anotherConnectionGetsTheLockWhileAPacedBulkWriterRuns)
    {
        TmpDatabase tmpDb;
        Session session{ tmpDb.getDb() };
        session.prepareTablesIfNeeded();
        const ClusterId clusterId{ createPacingTestCluster(session) };

        std::atomic<bool> started{};
        std::thread bulkWriter{ [&] {
            runBulkWriter(tmpDb.getDb(), clusterId, std::make_unique<WritePacer>(WritePacer::Settings{ .maxStretch = 500ms, .pause = 120ms }), 2s, 5ms, started);
        } };

        while (!started)
            std::this_thread::sleep_for(1ms);
        std::this_thread::sleep_for(300ms); // well inside a stretch

        Wt::Dbo::backend::Sqlite3 foreign{ tmpDb.getPath().string() };
        foreign.executeSql("PRAGMA busy_timeout=3000");

        const auto start{ std::chrono::steady_clock::now() };
        EXPECT_NO_THROW(foreign.executeSql("BEGIN IMMEDIATE"));
        const auto waited{ std::chrono::steady_clock::now() - start };
        EXPECT_NO_THROW(foreign.executeSql("COMMIT"));

        bulkWriter.join();

        // One stretch (500 ms) plus the transaction in flight, with room for a slow runner.
        EXPECT_LT(waited, 1500ms);
    }

    // The same for a writer inside the process -- an HTTP thread storing a rating -- which waits on
    // the in-process write mutex rather than on SQLite.
    TEST(WritePacer, anotherThreadGetsTheWriteMutexWhileAPacedBulkWriterRuns)
    {
        TmpDatabase tmpDb;
        Session session{ tmpDb.getDb() };
        session.prepareTablesIfNeeded();
        const ClusterId clusterId{ createPacingTestCluster(session) };

        std::atomic<bool> started{};
        std::thread bulkWriter{ [&] {
            runBulkWriter(tmpDb.getDb(), clusterId, std::make_unique<WritePacer>(WritePacer::Settings{ .maxStretch = 500ms, .pause = 120ms }), 2s, 5ms, started);
        } };

        while (!started)
            std::this_thread::sleep_for(1ms);
        std::this_thread::sleep_for(300ms);

        const auto start{ std::chrono::steady_clock::now() };
        {
            auto transaction{ session.createWriteTransaction() };
            Cluster::find(session, clusterId).modify()->setReleaseCount(1);
        }
        const auto waited{ std::chrono::steady_clock::now() - start };

        bulkWriter.join();

        EXPECT_LT(waited, 1500ms);
    }

    TEST(GuardedWrite, commitsAWriteThatSucceeds)
    {
        TmpDatabase tmpDb;
        Session session{ tmpDb.getDb() };
        session.prepareTablesIfNeeded();
        const ClusterId clusterId{ createPacingTestCluster(session) };

        bool failed{};
        EXPECT_TRUE(writeGuarded(session, [&] { Cluster::find(session, clusterId).modify()->setTrackCount(5); }, [&](const Wt::Dbo::Exception&) { failed = true; }));
        EXPECT_FALSE(failed);

        auto transaction{ session.createReadTransaction() };
        EXPECT_EQ(Cluster::find(session, clusterId)->getTrackCount(), 5);
    }

    // A refused write reports false instead of throwing, and does not leave its dirty objects
    // behind for the next write transaction on the thread to flush again.
    TEST(GuardedWrite, aRefusedWriteReturnsFalseAndLeavesTheSessionClean)
    {
        TmpDatabase tmpDb;
        Session session{ tmpDb.getDb() };
        session.prepareTablesIfNeeded();
        const ClusterId clusterId{ createPacingTestCluster(session) };

        std::size_t failures{};
        bool written{ true };
        EXPECT_NO_THROW(written = writeGuarded(
                            session, [&] {
                                Cluster::find(session, clusterId).modify()->setTrackCount(99);
                                session.execute("UPDATE no_such_table SET x = 1"); // what a refused statement looks like
                            },
                            [&](const Wt::Dbo::Exception&) { ++failures; }));
        EXPECT_FALSE(written);
        EXPECT_EQ(failures, 1);

        // The next write on this session must not carry the discarded update along.
        EXPECT_TRUE(writeGuarded(session, [&] { Cluster::find(session, clusterId).modify()->setReleaseCount(3); }, [](const Wt::Dbo::Exception&) {}));

        auto transaction{ session.createReadTransaction() };
        const Cluster::pointer cluster{ Cluster::find(session, clusterId) };
        EXPECT_EQ(cluster->getReleasesCount(), 3);
        EXPECT_NE(cluster->getTrackCount(), 99);
    }
} // namespace lms::db::tests
