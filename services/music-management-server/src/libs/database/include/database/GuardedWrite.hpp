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

#include <Wt/Dbo/Exception.h>

#include "database/Session.hpp"

namespace lms::db
{
    // Runs `write` in a write transaction of its own and reports whether it was committed.
    //
    // For background work -- podcasts, ListenBrainz -- that runs on a thread where an escaping
    // exception ends the process: the "Misc" IOContextRunner logs FATAL and calls std::abort()
    // (bug report 135). A write the database refuses, typically still locked by another writer
    // after busy_timeout, is a reason to try again on the next round, not to take playback down.
    //
    // The shape is the one bug report 132 settled on, and each part is load-bearing:
    // - the outer try covers the whole transaction scope: BEGIN IMMEDIATE throws from the
    //   constructor, and the commit from the destructor;
    // - the inner try sits inside the scope, and flushes explicitly, so that the destructor's
    //   commit (which runs even while an exception unwinds) finds nothing left to flush -- a throw
    //   from a destructor during unwinding would be std::terminate;
    // - both catches drop the unflushed changes: a failed flush leaves the objects dirty in the
    //   thread's session, and the next write transaction on that thread would try them again.
    //
    // `onFailure(const Wt::Dbo::Exception&)` is called on a refused write, before this returns
    // false; the caller logs, with its own module and wording. Only Wt::Dbo::Exception is caught.
    template<typename Write, typename OnFailure>
    bool writeGuarded(Session& session, const Write& write, const OnFailure& onFailure)
    {
        bool written{};
        bool reported{};
        try
        {
            // Throws from here when BEGIN IMMEDIATE times out; nothing was touched yet.
            auto transaction{ session.createWriteTransaction() };
            try
            {
                write();
                session.getDboSession()->flush();
                written = true;
            }
            catch (const Wt::Dbo::Exception& e)
            {
                session.getDboSession()->discardUnflushed();
                onFailure(e);
                reported = true;
            }
        } // commits here
        catch (const Wt::Dbo::Exception& e)
        {
            session.getDboSession()->discardUnflushed();
            if (!reported)
                onFailure(e);
            written = false;
        }

        return written;
    }
} // namespace lms::db
