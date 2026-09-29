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

#include <chrono>
#include <thread>

#include <gtest/gtest.h>

#include <Wt/Dbo/backend/Sqlite3.h>

#include "Common.hpp"

// Bug report 132: another process -- music-manager -- writing into lms.db while LMS writes to it.
// These tests hold the write lock on a second, raw SQLite connection, as music-manager does, and
// check what an LMS transaction does meanwhile.
namespace lms::db::tests
{
    namespace
    {
        // Stands in for music-manager: a separate connection that takes the write lock and gives
        // it back after `holdFor`, from another thread.
        class ForeignWriter
        {
        public:
            explicit ForeignWriter(const std::filesystem::path& dbPath)
                : _connection{ dbPath.string() }
            {
                _connection.executeSql("BEGIN IMMEDIATE");
            }

            ~ForeignWriter()
            {
                if (_releaser.joinable())
                    _releaser.join();
            }

            ForeignWriter(const ForeignWriter&) = delete;
            ForeignWriter& operator=(const ForeignWriter&) = delete;
            ForeignWriter(ForeignWriter&&) = delete;
            ForeignWriter& operator=(ForeignWriter&&) = delete;

            void releaseAfter(std::chrono::milliseconds holdFor)
            {
                _releaser = std::thread{ [this, holdFor] {
                    std::this_thread::sleep_for(holdFor);
                    _connection.executeSql("COMMIT");
                } };
            }

        private:
            Wt::Dbo::backend::Sqlite3 _connection;
            std::thread _releaser;
        };

        ClusterId createCluster(Session& session)
        {
            auto transaction{ session.createWriteTransaction() };
            const ClusterType::pointer type{ session.create<ClusterType>("Genre") };
            return session.create<Cluster>(type, "Hardstyle")->getId();
        }
    } // namespace

    // The crash itself: this step reads the cluster, then updates it. As a deferred transaction
    // the update was refused at once -- a read-to-write upgrade never waits for the busy handler
    // -- and "update cluster ...: database is locked" left the scanner thread uncaught. Started
    // with BEGIN IMMEDIATE, the transaction waits for the lock under busy_timeout instead.
    TEST(WriteTransactionLock, aReadThenWriteTransactionWaitsForAnotherConnectionsWriteLock)
    {
        TmpDatabase tmpDb;
        Session session{ tmpDb.getDb() };
        session.prepareTablesIfNeeded();
        const ClusterId clusterId{ createCluster(session) };

        const auto start{ std::chrono::steady_clock::now() };
        {
            ForeignWriter writer{ tmpDb.getPath() };
            writer.releaseAfter(std::chrono::milliseconds{ 300 });

            EXPECT_NO_THROW({
                auto transaction{ session.createWriteTransaction() };
                Cluster::pointer cluster{ Cluster::find(session, clusterId) };
                cluster.modify()->setTrackCount(42);
                cluster.modify()->setReleaseCount(7);
            });
        }
        EXPECT_GE(std::chrono::steady_clock::now() - start, std::chrono::milliseconds{ 250 });

        auto transaction{ session.createReadTransaction() };
        const Cluster::pointer cluster{ Cluster::find(session, clusterId) };
        ASSERT_TRUE(cluster);
        EXPECT_EQ(cluster->getTrackCount(), 42);
        EXPECT_EQ(cluster->getReleasesCount(), 7);
    }

    // Reads keep the deferred BEGIN: under WAL they must not queue behind a writer.
    TEST(WriteTransactionLock, aReadTransactionIsNotHeldUpByAnotherConnectionsWriteLock)
    {
        TmpDatabase tmpDb;
        Session session{ tmpDb.getDb() };
        session.prepareTablesIfNeeded();
        const ClusterId clusterId{ createCluster(session) };

        ForeignWriter writer{ tmpDb.getPath() };

        const auto start{ std::chrono::steady_clock::now() };
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_TRUE(Cluster::find(session, clusterId));
        }
        EXPECT_LT(std::chrono::steady_clock::now() - start, std::chrono::seconds{ 5 });

        writer.releaseAfter(std::chrono::milliseconds{ 0 });
    }

    // A write transaction nested in one that is already open does not try to begin a second
    // SQLite transaction on the same connection.
    TEST(WriteTransactionLock, aNestedWriteTransactionReusesTheOpenOne)
    {
        TmpDatabase tmpDb;
        Session session{ tmpDb.getDb() };
        session.prepareTablesIfNeeded();
        const ClusterId clusterId{ createCluster(session) };

        EXPECT_NO_THROW({
            auto outer{ session.createWriteTransaction() };
            auto inner{ session.createWriteTransaction() };
            Cluster::find(session, clusterId).modify()->setTrackCount(3);
        });

        auto transaction{ session.createReadTransaction() };
        EXPECT_EQ(Cluster::find(session, clusterId)->getTrackCount(), 3);
    }
} // namespace lms::db::tests
