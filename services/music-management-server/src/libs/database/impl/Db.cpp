/*
 * Copyright (C) 2019 Emeric Poupon
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
#include <functional>
#include <memory>

#include <Wt/Dbo/FixedSqlConnectionPool.h>
#include <Wt/Dbo/Logger.h>
#include <Wt/Dbo/backend/Sqlite3.h>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "database/Session.hpp"
#include "database/objects/User.hpp"

#include "Db.hpp"
#include "WriteTransactionBegin.hpp"

namespace lms::db
{
    namespace
    {
        class Connection : public Wt::Dbo::backend::Sqlite3
        {
        public:
            Connection(const std::filesystem::path& dbPath)
                : Wt::Dbo::backend::Sqlite3{ dbPath.string() }
                , _dbPath{ dbPath }
            {
                prepare();
            }

            Connection(const Connection& other)
                : Wt::Dbo::backend::Sqlite3{ other }
                , _dbPath{ other._dbPath }
            {
                prepare();
            }
            ~Connection() override = default;

            // A write transaction takes the write lock up front, so that it waits for another
            // writer (busy_timeout below) instead of failing at its first write -- see
            // WriteTransactionBegin.hpp. Read transactions keep Wt's deferred BEGIN: under WAL
            // they never take the write lock and must not queue behind one.
            void startTransaction() override
            {
                if (detail::isOpeningWriteTransaction())
                    executeSql("BEGIN IMMEDIATE");
                else
                    Wt::Dbo::backend::Sqlite3::startTransaction();
            }

        private:
            Connection& operator=(const Connection&) = delete;
            Connection(Connection&&) = delete;
            Connection&& operator=(Connection&&) = delete;

            std::unique_ptr<SqlConnection> clone() const override
            {
                return std::make_unique<Connection>(*this);
            }

            void prepare()
            {
                LMS_LOG(DB, DEBUG, "Setting per-connection settings...");
                executeSql("PRAGMA journal_mode=WAL");
                executeSql("PRAGMA synchronous=normal");
                // SQLite never shrinks the WAL file by itself: it rewinds to the start after a
                // checkpoint, but the file keeps the size of the longest stretch the log ever
                // had to hold without a checkpoint getting through -- 1.09 GB on production,
                // more than the 807 MB database. With a limit, the file is truncated back to it
                // whenever the log is reset. Only the file size changes: checkpoints run as
                // before (wal_autocheckpoint, 1000 pages) and no reader waits for anything
                // (bug report 134).
                executeSql("PRAGMA journal_size_limit=67108864");
                // Without this SQLite answers a held write lock with SQLITE_BUSY at once, and
                // at startup that surfaces as an uncaught exception from ANALYZE -- the process
                // dies, autoheal restarts it, and the next startup meets the same lock. muma
                // writes into this database on a schedule (users, playlists, artist images,
                // song versions) in transactions of a few seconds, and two such writes cost
                // this server 102 and 43 restarts in one day. Waiting is the whole fix: WAL
                // already lets readers through, so this only ever serialises two writers.
                // It covers write transactions only because they begin with BEGIN IMMEDIATE
                // (startTransaction above): a deferred transaction that has already read is
                // refused at once on its first write, whatever the timeout (bug report 132).
                executeSql("PRAGMA busy_timeout=15000");
                executeSql("PRAGMA uri=ON");
                executeSql("ATTACH DATABASE 'file::memory:?cache=shared' AS volatile");
                LMS_LOG(DB, DEBUG, "Setting per-connection settings done!");
            }

            std::filesystem::path _dbPath;
        };

        enum class IntegrityCheckType
        {
            Quick,
            Full
        };
        bool checkDbIntegrity(Wt::Dbo::SqlConnection& connection, IntegrityCheckType checkType, std::function<void(std::string_view error)> errorCallback)
        {
            bool integrityCheckPassed{};

            auto statement = connection.prepareStatement(checkType == IntegrityCheckType::Full ? "PRAGMA integrity_check" : "PRAGMA quick_check");
            statement->execute();

            std::string result;
            result.reserve(32);
            while (statement->nextRow())
            {
                result.clear();
                statement->getResult(0, &result, result.capacity());

                if (result == "ok")
                {
                    integrityCheckPassed = true;
                    break;
                }

                errorCallback(result);
            }

            return integrityCheckPassed;
        }

        bool checkDbForeignKeyConstraints(Wt::Dbo::SqlConnection& connection, std::function<void(std::string_view table, long long rowId, std::string_view referredTable)> errorCallback)
        {
            bool foreignKeyConstraintsPassed{ true };

            auto statement = connection.prepareStatement("PRAGMA foreign_key_check");
            statement->execute();

            std::string table;
            std::string foreignTable;
            // see https://www.sqlite.org/pragma.html#pragma_foreign_key_check for expected result
            while (statement->nextRow())
            {
                foreignKeyConstraintsPassed = false;

                table.clear();
                foreignTable.clear();
                long long rowId{};

                statement->getResult(0, &table, static_cast<int>(table.capacity()));
                statement->getResult(1, &rowId);
                statement->getResult(2, &foreignTable, static_cast<int>(foreignTable.capacity()));

                errorCallback(table, rowId, foreignTable);
            }

            return foreignKeyConstraintsPassed;
        }

        std::optional<int> getPageSize(Wt::Dbo::SqlConnection& connection)
        {
            auto statement = connection.prepareStatement("PRAGMA page_size");
            statement->execute();

            std::optional<int> res;
            while (statement->nextRow())
            {
                assert(!res);
                int value{};
                if (statement->getResult(0, &value))
                    res = value;
                break;
            }

            return res;
        }

        std::optional<int> getCacheSize(Wt::Dbo::SqlConnection& connection)
        {
            auto statement = connection.prepareStatement("PRAGMA cache_size");
            statement->execute();

            std::optional<int> res;
            while (statement->nextRow())
            {
                assert(!res);
                int value{};
                if (statement->getResult(0, &value))
                    res = value;
                break;
            }

            return res;
        }

        void getCompileOptions(Wt::Dbo::SqlConnection& connection, std::function<void(std::string_view compileOption)> callback)
        {
            auto statement = connection.prepareStatement("PRAGMA compile_options");
            statement->execute();

            std::string res;
            while (statement->nextRow())
            {
                res.clear();

                if (statement->getResult(0, &res, static_cast<int>(res.capacity())))
                    callback(res);
            }
        }

        // One per Db ever created in this process; never reused, unlike an address.
        std::uint64_t nextInstanceId()
        {
            static std::atomic<std::uint64_t> lastInstanceId{};
            return ++lastInstanceId;
        }
    } // namespace

    std::unique_ptr<IDb> createDb(const std::filesystem::path& dbPath, std::size_t connectionCount)
    {
        return std::make_unique<Db>(dbPath, connectionCount);
    }

    // Session living class handling the database and the login
    Db::Db(const std::filesystem::path& dbPath, std::size_t connectionCount)
        : _instanceId{ nextInstanceId() }
    {
        Wt::Dbo::logToWt();

        std::string checkType{ "quick" };
        LMS_LOG(DB, INFO, "Creating connection pool on file " << dbPath);

        auto connection{ std::make_unique<Connection>(dbPath) };
        if (core::IConfig * config{ core::Service<core::IConfig>::get() }) // may not be here on testU
        {
            connection->setProperty("show-queries", config->getBool("db-show-queries", false) ? "true" : "false");
            checkType = config->getString("db-integrity-check", "quick");
        }

        auto connectionPool{ std::make_unique<Wt::Dbo::FixedSqlConnectionPool>(std::move(connection), connectionCount) };
        connectionPool->setTimeout(std::chrono::seconds{ 10 });

        _connectionPool = std::move(connectionPool);

        executeSql("PRAGMA temp_store=MEMORY");
        executeSql("PRAGMA cache_size=-8000");
        executeSql("PRAGMA automatic_index=0");

        logPageSize();
        logCacheSize();
        logCompileOptions();
        if (checkType == "quick")
        {
            performQuickCheck();
        }
        else if (checkType == "full")
        {
            performIntegrityCheck();
            performForeignKeyConstraintsCheck();
        }
        else if (checkType != "none")
        {
            throw Exception("Invalid 'db-integrity-check' value: '" + checkType + "'. Expected 'quick', 'full' or 'none'.");
        }
    }

    void Db::executeSql(const std::string& sql)
    {
        ScopedConnection connection{ *_connectionPool };
        connection->executeSql(sql);
    }

    Session& Db::getTLSSession()
    {
        // The thread's session belongs to one Db, which owns it. The cache used to be the bare
        // pointer, so once that Db was destroyed and another created -- every test suite opens a
        // database of its own -- the next call on the same thread returned a session freed with
        // the old Db. Keyed by the instance id, not the address: a new Db can reuse the old one's.
        struct TlsSession
        {
            std::uint64_t dbInstanceId{};
            Session* session{};
        };
        static thread_local TlsSession tls;

        if (!tls.session || tls.dbInstanceId != _instanceId)
        {
            auto newSession{ std::make_unique<Session>(*this) };
            tls = TlsSession{ .dbInstanceId = _instanceId, .session = newSession.get() };

            {
                std::scoped_lock lock{ _tlsSessionsMutex };
                _tlsSessions.push_back(std::move(newSession));
            }
        }

        return *tls.session;
    }

    void Db::logPageSize()
    {
        ScopedConnection connection{ *_connectionPool };
        const std::optional<int> pageSize{ getPageSize(*connection) };

        if (pageSize)
            LMS_LOG(DB, INFO, "Page size set to " << *pageSize);
    }

    void Db::logCacheSize()
    {
        ScopedConnection connection{ *_connectionPool };
        const std::optional<int> cacheSize{ getCacheSize(*connection) };

        if (cacheSize)
            LMS_LOG(DB, INFO, "Cache size set to " << *cacheSize);
    }

    void Db::logCompileOptions()
    {
        ScopedConnection connection{ *_connectionPool };

        LMS_LOG(DB, INFO, "Sqlite3 compile options:");
        getCompileOptions(*connection, [](std::string_view compileOption) {
            LMS_LOG(DB, INFO, compileOption);
        });
    }

    void Db::performQuickCheck()
    {
        ScopedConnection connection{ *_connectionPool };

        LMS_LOG(DB, INFO, "Performing quick database check...");

        // Quick check is just a simple integrity check
        const bool quickCheckPassed{ checkDbIntegrity(*connection, IntegrityCheckType::Quick, [&](std::string_view error) {
            LMS_LOG(DB, ERROR, "Quick check error: " << error);
        }) };

        if (quickCheckPassed)
            LMS_LOG(DB, INFO, "Quick database check passed!");
        else
            LMS_LOG(DB, ERROR, "Quick database check done with errors!");
    }

    void Db::performIntegrityCheck()
    {
        ScopedConnection connection{ *_connectionPool };

        LMS_LOG(DB, INFO, "Checking database integrity...");

        const bool integrityCheckPassed{ checkDbIntegrity(*connection, IntegrityCheckType::Full, [&](std::string_view error) {
            LMS_LOG(DB, ERROR, "Integrity check error: " << error);
        }) };

        if (integrityCheckPassed)
            LMS_LOG(DB, INFO, "Database integrity check passed!");
        else
            LMS_LOG(DB, ERROR, "Database integrity check done with errors!");
    }

    void Db::performForeignKeyConstraintsCheck()
    {
        ScopedConnection connection{ *_connectionPool };

        LMS_LOG(DB, INFO, "Checking foreign key constraints...");

        const bool foreignKeyConstraintsPassed{ checkDbForeignKeyConstraints(*connection, [&](std::string_view table, long long rowId, std::string_view referredTable) {
            LMS_LOG(DB, ERROR, "Foreign key constraint failed in table '" << table << "', rowid = " << rowId << ", referred table = '" << referredTable << "'");
        }) };

        if (!foreignKeyConstraintsPassed)
            throw Exception("Foreign key constraints check failed! Please restore from a backup or recreate the database.");

        LMS_LOG(DB, INFO, "Foreign key constraints check passed!");
    }

    Db::ScopedConnection::ScopedConnection(Wt::Dbo::SqlConnectionPool& pool)
        : _connectionPool{ pool }
        , _connection{ _connectionPool.getConnection() }
    {
    }

    Db::ScopedConnection::~ScopedConnection()
    {
        _connectionPool.returnConnection(std::move(_connection));
    }

    Wt::Dbo::SqlConnection* Db::ScopedConnection::operator->() const
    {
        return _connection.get();
    }

} // namespace lms::db
