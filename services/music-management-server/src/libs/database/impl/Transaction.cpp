/*
 * Copyright (C) 2025 Emeric Poupon
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

#include "database/Transaction.hpp"

#include <cassert>

#include "core/RecursiveSharedMutex.hpp"
#include "database/WritePacer.hpp"

#include "TransactionChecker.hpp"
#include "WriteTransactionBegin.hpp"

namespace lms::db
{
    namespace
    {
        bool& openingWriteTransaction()
        {
            thread_local bool opening{};
            return opening;
        }

        // Opens the SQLite transaction now, as BEGIN IMMEDIATE (see WriteTransactionBegin.hpp),
        // rather than letting Wt open it lazily, as a deferred BEGIN, on the first statement.
        // When this write transaction is nested in one already open on the session, Wt's open()
        // is a no-op and the outer transaction keeps the mode it was opened with.
        //
        // If the write lock stays taken past busy_timeout, BEGIN IMMEDIATE throws from here, i.e.
        // from the WriteTransaction constructor, before anything was read or written. Wt then
        // rolls back a transaction it regards as open and logs the "no transaction is active"
        // error that rollback gets; the exception reaches the caller unchanged.
        void beginImmediately(Wt::Dbo::Transaction& transaction)
        {
            struct Scope
            {
                Scope() { openingWriteTransaction() = true; }
                ~Scope() { openingWriteTransaction() = false; }
                Scope(const Scope&) = delete;
                Scope& operator=(const Scope&) = delete;
                Scope(Scope&&) = delete;
                Scope& operator=(Scope&&) = delete;
            };

            const Scope scope;
            transaction.connection(); // opens the transaction if it is not open yet
        }
    } // namespace

    namespace detail
    {
        bool isOpeningWriteTransaction()
        {
            return openingWriteTransaction();
        }
    } // namespace detail

    namespace detail
    {
        WritePacingScope::WritePacingScope(WritePacer* pacer)
            : _pacer{ pacer }
        {
            if (_pacer)
                _pacer->onWriteBegin();
        }

        WritePacingScope::~WritePacingScope()
        {
            if (_pacer)
                _pacer->onWriteEnd();
        }
    } // namespace detail

    WriteTransaction::WriteTransaction(core::RecursiveSharedMutex& mutex, Wt::Dbo::Session& session, WritePacer* pacer)
        : _pacing{ pacer }
        , _lock{ mutex }
        , _trace{ "Database", core::tracing::Level::Detailed, "WriteTransaction" }
        , _transaction{ session }
    {
        beginImmediately(_transaction);
#if LMS_CHECK_TRANSACTION_ACCESSES
        TransactionChecker::pushWriteTransaction(_transaction.session());
#endif
    }

    WriteTransaction::WriteTransaction(std::unique_lock<core::RecursiveSharedMutex>&& lock, Wt::Dbo::Session& session)
        : _pacing{ nullptr } // the lock is already taken: too late to pace
        , _lock{ std::move(lock) }
        , _trace{ "Database", core::tracing::Level::Detailed, "WriteTransaction" }
        , _transaction{ session }
    {
        assert(_lock.owns_lock());
        beginImmediately(_transaction);
#if LMS_CHECK_TRANSACTION_ACCESSES
        TransactionChecker::pushWriteTransaction(_transaction.session());
#endif
    }

    WriteTransaction::~WriteTransaction()
    {
#if LMS_CHECK_TRANSACTION_ACCESSES
        TransactionChecker::popWriteTransaction(_transaction.session());
#endif

        core::tracing::ScopedTrace _trace{ "Database", core::tracing::Level::Detailed, "Commit" };
        _transaction.commit();
    }

    ReadTransaction::ReadTransaction(Wt::Dbo::Session& session)
        : _trace{ "Database", core::tracing::Level::Detailed, "ReadTransaction" }
        , _transaction{ session }
    {
#if LMS_CHECK_TRANSACTION_ACCESSES
        TransactionChecker::pushReadTransaction(_transaction.session());
#endif
    }

    ReadTransaction::~ReadTransaction()
    {
#if LMS_CHECK_TRANSACTION_ACCESSES
        TransactionChecker::popReadTransaction(_transaction.session());
#endif
    }
} // namespace lms::db
