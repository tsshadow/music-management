/*
 * Copyright (C) 2021 Emeric Poupon
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
#include <shared_mutex>
#include <thread>
#include <unordered_map>

namespace lms::core
{
    // API compatible with shared_mutex
    class RecursiveSharedMutex
    {
    public:
        void lock();
        // Takes the unique lock only if nobody else holds it, never waits. For writes that are
        // bookkeeping (a last-used stamp, a last-login time): skipping one is harmless, queueing
        // an HTTP thread behind a scanner batch for it is not.
        bool try_lock();
        void unlock();

        void lock_shared();
        void unlock_shared();

#ifndef NDEBUG
        bool isSharedLocked();
        bool isUniqueLocked();
#endif // NDEBUG
    private:
        std::shared_mutex _mutex;
        std::thread::id _uniqueOwner;
        std::size_t _uniqueCount{};

        std::mutex _sharedCountMutex;
        std::unordered_map<std::thread::id, std::size_t> _sharedCounts;
    };
} // namespace lms::core
