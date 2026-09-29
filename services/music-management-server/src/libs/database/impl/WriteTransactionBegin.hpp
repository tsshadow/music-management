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

#pragma once

namespace lms::db::detail
{
    // True while a WriteTransaction is opening its SQLite transaction on the calling thread.
    //
    // The connection reads this to start that transaction with BEGIN IMMEDIATE instead of
    // Wt's plain (deferred) BEGIN. A deferred transaction reads before it writes, and SQLite
    // answers the read-to-write upgrade with SQLITE_BUSY at once while another connection --
    // music-manager writes into lms.db directly -- holds the write lock: the busy handler is
    // only consulted by a connection that has no transaction open yet. BEGIN IMMEDIATE takes
    // the write lock while none is open, so PRAGMA busy_timeout applies to it (bug report 132).
    bool isOpeningWriteTransaction();
} // namespace lms::db::detail
