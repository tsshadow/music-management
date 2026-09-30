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

#pragma once

#include <mutex>

#include <Wt/Dbo/Transaction.h>

#include "core/ITraceLogger.hpp"

namespace lms::core
{
    class RecursiveSharedMutex;
}

namespace lms::db
{
    class WritePacer;

    namespace detail
    {
        // Tells a WritePacer (if any) that a write transaction begins and, when destroyed, that
        // it ended. A member of WriteTransaction declared before the lock, so that the pacer
        // runs before the write mutex is taken and after it has been given back.
        class WritePacingScope
        {
        public:
            explicit WritePacingScope(WritePacer* pacer);
            ~WritePacingScope();
            WritePacingScope(const WritePacingScope&) = delete;
            WritePacingScope& operator=(const WritePacingScope&) = delete;
            WritePacingScope(WritePacingScope&&) = delete;
            WritePacingScope& operator=(WritePacingScope&&) = delete;

        private:
            WritePacer* const _pacer;
        };
    } // namespace detail

    class WriteTransaction
    {
    public:
        ~WriteTransaction();

    private:
        friend class Session;
        // `pacer` may be null: only a bulk writer's session has one (see WritePacer).
        WriteTransaction(core::RecursiveSharedMutex& mutex, Wt::Dbo::Session& session, WritePacer* pacer);
        // Takes a lock the caller already holds (see Session::tryCreateWriteTransaction).
        WriteTransaction(std::unique_lock<core::RecursiveSharedMutex>&& lock, Wt::Dbo::Session& session);

        WriteTransaction(const WriteTransaction&) = delete;
        WriteTransaction& operator=(const WriteTransaction&) = delete;

        const detail::WritePacingScope _pacing; // before the lock
        const std::unique_lock<core::RecursiveSharedMutex> _lock;
        const core::tracing::ScopedTrace _trace; // before actual transaction
        Wt::Dbo::Transaction _transaction;
    };

    class ReadTransaction
    {
    public:
        ~ReadTransaction();

    private:
        friend class Session;
        ReadTransaction(Wt::Dbo::Session& session);

        ReadTransaction(const ReadTransaction&) = delete;
        ReadTransaction& operator=(const ReadTransaction&) = delete;

        const core::tracing::ScopedTrace _trace; // before actual transaction
        Wt::Dbo::Transaction _transaction;
    };
} // namespace lms::db
