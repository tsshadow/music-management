/*
 * Copyright (C) 2013 Emeric Poupon
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

#include <Wt/Dbo/Session.h>

#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "database/Transaction.hpp"
#include "database/Types.hpp"

namespace lms::db
{
    class IDb;
    class WritePacer;
    class Session
    {
    public:
        Session(IDb& db);
        ~Session();
        Session(const Session&) = delete;
        Session& operator=(const Session&) = delete;

        [[nodiscard]] WriteTransaction createWriteTransaction();
        // A write transaction if the process-wide write lock is free right now, nothing if it is
        // not. Never waits: for a write that may be skipped (bookkeeping), so the caller does not
        // queue behind a scanner batch that holds the lock for seconds at a time.
        [[nodiscard]] std::unique_ptr<WriteTransaction> tryCreateWriteTransaction();
        [[nodiscard]] ReadTransaction createReadTransaction();

        // Paces every write transaction this session opens from now on, see WritePacer. For a
        // bulk writer (the scanner) that would otherwise keep the write lock to itself. Null
        // turns pacing off. tryCreateWriteTransaction is never paced: it does not wait at all.
        void setWritePacer(std::unique_ptr<WritePacer> pacer);
        WritePacer* getWritePacer() { return _writePacer.get(); }

        void checkWriteTransaction() const;
        void checkReadTransaction() const;

        void execute(std::string_view statement);

        // All these methods will acquire transactions
        void fullAnalyze(); // helper for retrieveEntriesToAnalyze + analyzeEntry
        void retrieveEntriesToAnalyze(std::vector<std::string>& entryList);
        void analyzeEntry(const std::string& entry);

        bool areAllTablesEmpty(); // need to acquire a read transaction
        FileStats getFileStats(); // need to acquire a read transaction

        void prepareTablesIfNeeded(); // need to run only once at startup
        bool migrateSchemaIfNeeded(); // returns true if migration was performed
        void createIndexesIfNeeded();
        void vacuumIfNeeded();
        void vacuum();

        // returning a ptr here to ease further wrapping using operator->
        Wt::Dbo::Session* getDboSession() { return &_session; }
        const Wt::Dbo::Session* getDboSession() const { return &_session; }

        IDb& getDb() { return _db; }

        template<typename Object, typename... Args>
        typename Object::pointer create(Args&&... args)
        {
            checkWriteTransaction();

            typename Object::pointer res{ Object::create(*this, std::forward<Args>(args)...) };
            getDboSession()->flush();

            return res;
        }

        template<typename Object>
        void destroy(typename Object::IdType id)
        {
            destroy<Object>(std::span{ &id, 1 });
        }

        template<typename Object>
        void destroy(std::span<const typename Object::IdType> ids)
        {
            checkWriteTransaction();

            const std::string query{ std::string{ "DELETE FROM " } + _session.tableName<Object>() + " WHERE id = ?" };
            for (typename Object::IdType id : ids)
                execute(query, id.getValue());
        }

    private:
        // The process-wide lock every write transaction takes.
        core::RecursiveSharedMutex& getWriteMutex();
        void execute(std::string_view query, long long id);

        IDb& _db;
        Wt::Dbo::Session _session;
        std::unique_ptr<WritePacer> _writePacer;
    };
} // namespace lms::db
