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

#include "AuthTokenService.hpp"

#include <Wt/Dbo/Exception.h>

#include <Wt/Auth/HashFunction.h>
#include <Wt/WRandom.h>

#include "core/ILogger.hpp"
#include "database/Session.hpp"
#include "database/objects/AuthToken.hpp"
#include "database/objects/User.hpp"
#include "services/auth/Types.hpp"

namespace lms::auth
{
    namespace
    {
        // How stale last_used may be before a request rewrites it. One write a minute per
        // token instead of one per request, which is what keeps this off the hot path.
        constexpr int LAST_USED_GRANULARITY_SECS{ 60 };

        AuthTokenService::AuthTokenInfo createAuthTokenInfo(const db::AuthToken::pointer& authToken)
        {
            return AuthTokenService::AuthTokenInfo{
                .userId = authToken->getUserId(),
                .expiry = authToken->getExpiry(),
                .lastUsed = authToken->getLastUsed(),
                .useCount = authToken->getUseCount(),
                .maxUseCount = authToken->getMaxUseCount(),
            };
        }
    } // namespace

    std::unique_ptr<IAuthTokenService> createAuthTokenService(db::IDb& db, std::size_t maxThrottlerEntryCount)
    {
        return std::make_unique<AuthTokenService>(db, maxThrottlerEntryCount);
    }

    AuthTokenService::AuthTokenService(db::IDb& db, std::size_t maxThrottlerEntryCount)
        : AuthServiceBase{ db }
        , _loginThrottler{ maxThrottlerEntryCount }
    {
    }

    void AuthTokenService::registerDomain(core::LiteralString domain, const DomainParameters& params)
    {
        [[maybe_unused]] auto [it, inserted]{ _domainParameters.emplace(domain, params) };
        if (!inserted)
            throw Exception{ "Auth token domain already registered!" };
    }

    void AuthTokenService::createAuthToken(core::LiteralString domain, db::UserId userId, std::string_view token)
    {
        const DomainParameters& params{ getDomainParameters(domain) };

        db::Session& session{ getDbSession() };
        const auto now{ Wt::WDateTime::currentDateTime() };
        const auto expiry{ params.tokenDuration ? now.addSecs(std::chrono::duration_cast<std::chrono::seconds>(params.tokenDuration.value()).count()) : Wt::WDateTime{} };

        {
            auto transaction{ session.createWriteTransaction() };

            const db::User::pointer user{ db::User::find(session, userId) };
            if (!user)
                throw Exception{ "User deleted" };

            const db::AuthToken::pointer authToken{ session.create<db::AuthToken>(domain.str(), token, expiry, params.tokenMaxUseCount, user) };

            LMS_LOG(UI, DEBUG, "Created auth token for user '" << user->getLoginName() << "', expiry = " << authToken->getExpiry().toString() << ", maxUseCount = " << (authToken->getMaxUseCount() ? std::to_string(*authToken->getMaxUseCount()) : "<unset>"));

            // TODO per domain
            if (db::AuthToken::getCount(session, user->getId()) >= 50)
                db::AuthToken::removeExpiredTokens(session, domain.str(), Wt::WDateTime::currentDateTime());
        }
    }

    std::optional<AuthTokenService::AuthTokenInfo> AuthTokenService::processAuthToken(core::LiteralString domain, std::string_view token)
    {
        db::Session& session{ getDbSession() };

        // Resolve the token under a read transaction first, which takes no lock at all. An unknown
        // token is the normal case whenever a client is stuck on a stale key, and a write
        // transaction takes the process-wide exclusive lock (see Session::createWriteTransaction),
        // queueing behind every other writer -- the scanner above all, which writes in batches for
        // the whole length of a scan. Resolving a key that was never issued used to park an HTTP
        // thread there, several times a minute, for as long as the client kept retrying.
        {
            auto readTransaction{ session.createReadTransaction() };

            if (!db::AuthToken::find(session, domain.str(), token))
                return std::nullopt;
        }

        auto transaction{ session.createWriteTransaction() };

        // Looked up again: the read transaction above was released before this one was taken, so
        // the token may have been removed in between (expiry sweep, use count, user deletion).
        db::AuthToken::pointer authToken{ db::AuthToken::find(session, domain.str(), token) };
        if (!authToken)
            return std::nullopt;

        if (authToken->getExpiry().isValid() && authToken->getExpiry() < Wt::WDateTime::currentDateTime())
        {
            authToken.remove();
            return std::nullopt;
        }

        LMS_LOG(UI, DEBUG, "Found auth token for user ID '" << authToken->getUserId().getValue() << "' on domain '" << domain.str() << "'");

        AuthTokenInfo res{ createAuthTokenInfo(authToken) };

        // Every authenticated request used to write here: bump use_count, stamp last_used.
        // Dbo versions the row, so two requests carrying the same token -- the app's home
        // screen fires several at once -- both load version N, the second write throws
        // StaleObjectException, and that request is aborted with "Uncaught exception from
        // handleRequest". Nine of those in one hour on one token, every one of them a
        // failed call the user saw.
        //
        // The write only matters when something reads it: a token with a use limit needs
        // the count, and last_used needs to move now and then, not on every call. Everything
        // else stays a read.
        const auto now{ Wt::WDateTime::currentDateTime() };
        const bool countMatters{ authToken->getMaxUseCount().has_value() };
        const bool stampIsStale{ !authToken->getLastUsed().isValid() || authToken->getLastUsed().secsTo(now) >= LAST_USED_GRANULARITY_SECS };

        if (countMatters || stampIsStale)
        {
            // The pointer is this thread's cached copy -- Dbo keeps objects per session, and the
            // session is per thread (Db::getTLSSession) -- so it may date from an earlier request
            // on this thread, at a version another thread has since moved on. Writing on top of
            // that copy is the stale write below. Rereading here, under the process-wide write
            // lock, makes the bump land on what the row holds now.
            authToken.reread();
            try
            {
                const std::size_t tokenUseCount{ authToken.modify()->incUseCount() };
                authToken.modify()->setLastUsed(now);

                if (auto maxUseCount{ authToken->getMaxUseCount() })
                {
                    if (*maxUseCount >= tokenUseCount)
                        authToken.remove();
                }

                // Flushed here, inside the try. The transaction's own flush runs from
                // WriteTransaction's destructor at the end of this function, outside every catch,
                // which is how a StaleObjectException reached handleRequest as "Uncaught exception".
                session.getDboSession()->flush();
            }
            catch (const Wt::Dbo::StaleObjectException&)
            {
                // A concurrent writer got there first; its bump is as good as ours, the token was
                // valid when we looked, and failing the caller over bookkeeping cannot be right.
                //
                // The copy has to go, not only the exception: a failed flush leaves the object
                // dirty and stale in this thread's session (Transaction::rollback does not reread),
                // and Session::flush flushes every dirty object, so the *next* write transaction
                // on this thread -- a scrobble, a stream, whatever -- would throw the same stale
                // write again, until the process restarts. That is what poisoned one HTTP thread
                // with "Stale object, auth_token, id = 4, version = 2392" on every request it got.
                authToken.reread();
                LMS_LOG(UI, WARNING, "Auth token bump lost a race with a concurrent writer; dropped");
            }
        }

        return res;
    }

    AuthTokenService::AuthTokenProcessResult AuthTokenService::processAuthToken(core::LiteralString domain, const boost::asio::ip::address& clientAddress, std::string_view tokenValue)
    {
        // Do not waste too much resource on brute force attacks (optim)
        {
            std::shared_lock lock{ _mutex };

            if (_loginThrottler.isClientThrottled(clientAddress))
                return AuthTokenProcessResult{ .state = AuthTokenProcessResult::State::Throttled, .authTokenInfo = std::nullopt };
        }

        auto res{ processAuthToken(domain, tokenValue) };
        {
            std::unique_lock lock{ _mutex };

            if (_loginThrottler.isClientThrottled(clientAddress))
                return AuthTokenProcessResult{ .state = AuthTokenProcessResult::State::Throttled, .authTokenInfo = std::nullopt };

            if (!res)
            {
                _loginThrottler.onBadClientAttempt(clientAddress);
                return AuthTokenProcessResult{ .state = AuthTokenProcessResult::State::Denied, .authTokenInfo = std::nullopt };
            }

            _loginThrottler.onGoodClientAttempt(clientAddress);
            onUserAuthenticated(res->userId);
            return AuthTokenProcessResult{ .state = AuthTokenProcessResult::State::Granted, .authTokenInfo = res };
        }
    }

    void AuthTokenService::visitAuthTokens(core::LiteralString domain, db::UserId userId, std::function<void(const AuthTokenInfo& info, std::string_view token)> visitor)
    {
        db::Session& session{ getDbSession() };

        {
            auto transaction{ session.createReadTransaction() };

            db::AuthToken::find(session, domain.str(), userId, [&](const db::AuthToken::pointer& authToken) {
                const AuthTokenInfo info{ createAuthTokenInfo(authToken) };
                visitor(info, authToken->getValue());
            });
        }
    }

    void AuthTokenService::clearAuthTokens(core::LiteralString domain, db::UserId userId)
    {
        db::Session& session{ getDbSession() };

        {
            auto transaction{ session.createWriteTransaction() };
            db::AuthToken::clearUserTokens(session, domain.str(), userId);
        }
    }

    const AuthTokenService::DomainParameters& AuthTokenService::getDomainParameters(core::LiteralString domain) const
    {
        auto it{ _domainParameters.find(domain) };
        if (it == std::cend(_domainParameters))
            throw Exception{ "Invalid auth token domain" };

        return it->second;
    }
} // namespace lms::auth
