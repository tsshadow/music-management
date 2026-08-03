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

#pragma once

#include <shared_mutex>

#include "AuthServiceBase.hpp"
#include "LoginThrottler.hpp"
#include "services/auth/IPasswordService.hpp"

namespace lms::db
{
    class IDb;
    class Session;
} // namespace lms::db

namespace lms::auth
{
    // What the backend made of the credentials it was handed. Deliberately not a bool:
    // "I could not ask" and "the password is wrong" must not collapse into the same answer,
    // because only the second one is a failed login attempt.
    enum class PasswordCheckOutcome
    {
        Match,
        Mismatch,
        // The backend itself rate-limited this check (it owns the per-account budget).
        Throttled,
        // Unreachable, timed out, or answered something we cannot interpret.
        BackendError,
    };

    class PasswordServiceBase : public IPasswordService, public AuthServiceBase
    {
    public:
        // useLoginThrottler: false for backends that do their own rate limiting. LMS's throttler
        // keys on the client address, which for Subsonic traffic is the internal reverse-proxy
        // hop - one shared budget for every user - so it must not be stacked on top of a backend
        // that already limits per account.
        PasswordServiceBase(db::IDb& db, std::size_t maxThrottlerEntries, bool useLoginThrottler = true);

        ~PasswordServiceBase() override = default;
        PasswordServiceBase(const PasswordServiceBase&) = delete;
        PasswordServiceBase& operator=(const PasswordServiceBase&) = delete;
        PasswordServiceBase(PasswordServiceBase&&) = delete;
        PasswordServiceBase& operator=(PasswordServiceBase&&) = delete;

    private:
        virtual PasswordCheckOutcome checkUserPassword(std::string_view loginName, std::string_view password) = 0;

        CheckResult checkUserPassword(const boost::asio::ip::address& clientAddress,
                                      std::string_view loginName,
                                      std::string_view password) override;

        std::shared_mutex _mutex;
        LoginThrottler _loginThrottler;
        const bool _useLoginThrottler;
    };
} // namespace lms::auth
