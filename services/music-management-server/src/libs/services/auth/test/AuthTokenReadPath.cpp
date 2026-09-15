/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <chrono>
#include <future>
#include <memory>

#include <boost/asio/ip/address.hpp>
#include <gtest/gtest.h>

#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/AuthToken.hpp"
#include "services/auth/IAuthTokenService.hpp"

#include "Common.hpp"

namespace lms::auth::tests
{
    class AuthTokenReadPath : public db::tests::DatabaseFixture
    {
    };

    // Resolving a key used to open a write transaction before it knew whether the key existed, and
    // a write transaction takes the process-wide exclusive lock in Session.cpp. That queues behind
    // every other writer -- the scanner above all, which writes in batches for the whole length of
    // a scan. A client stuck on a stale key retries several times a minute forever, so each of
    // those retries parked an HTTP thread behind the scan for nothing.
    //
    // Holding a write transaction open here is what a scan batch does. If resolving an unknown key
    // still asks for the write lock, it cannot finish until that batch lets go.
    TEST_F(AuthTokenReadPath, anUnknownTokenDoesNotQueueBehindAWriter)
    {
        std::unique_ptr<IAuthTokenService> authTokenService{ createAuthTokenService(session.getDb(), 10) };

        db::IDb& db{ session.getDb() };
        std::promise<void> writerHoldsTheLock;
        std::promise<void> releaseTheWriter;

        auto writer{ std::async(std::launch::async, [&] {
            auto transaction{ db.getTLSSession().createWriteTransaction() };

            writerHoldsTheLock.set_value();
            releaseTheWriter.get_future().wait();
        }) };

        writerHoldsTheLock.get_future().wait();

        auto pending{ std::async(std::launch::async, [&] {
            return authTokenService->processAuthToken("subsonic", boost::asio::ip::make_address("192.0.2.1"), "a-token-that-was-never-issued");
        }) };

        const auto status{ pending.wait_for(std::chrono::seconds{ 10 }) };

        // Let the writer go before asserting, so a regression fails the test instead of wedging the
        // whole suite on a still-running thread.
        releaseTheWriter.set_value();
        writer.wait();

        ASSERT_EQ(status, std::future_status::ready) << "resolving an unknown token waited for the write lock";
        EXPECT_EQ(pending.get().state, IAuthTokenService::AuthTokenProcessResult::State::Denied);
    }

    // Dbo caches objects per session, and Db hands each thread its own session. A thread that
    // resolved a token once keeps that copy; when another thread bumps the row (use count, last
    // used), the copy is a version behind, and the next bump written on top of it is refused as a
    // stale write. That refusal used to surface twice over: once as the "Uncaught exception from
    // handleRequest" that failed the request in hand, and then on every later write transaction
    // of the same thread, because the stale object stayed dirty in the session and every commit
    // flushed it again -- one HTTP thread answering 500 to everything it was given, whatever the
    // request, until the process restarted.
    TEST_F(AuthTokenReadPath, aTokenBumpedOnAnotherThreadIsRereadNotRefused)
    {
        std::unique_ptr<IAuthTokenService> authTokenService{ createAuthTokenService(session.getDb(), 10) };
        authTokenService->registerDomain("subsonic", IAuthTokenService::DomainParameters{});

        db::tests::ScopedUser user{ session, "MyUser" };
        const boost::asio::ip::address client{ boost::asio::ip::make_address("192.0.2.1") };

        authTokenService->createAuthToken("subsonic", user.getId(), "the-token");

        // Dbo drops a cached object as soon as nothing points at it, so something has to keep
        // this thread's copy alive across the other thread's write for the copy to be stale at
        // all -- in production that is whatever earlier request on the thread left a pointer
        // behind. Here it is this one, taken under a read transaction: version 1, never used.
        db::Session& thisThread{ session.getDb().getTLSSession() };
        db::AuthToken::pointer keptAlive;
        {
            auto transaction{ thisThread.createReadTransaction() };
            keptAlive = db::AuthToken::find(thisThread, "subsonic", "the-token");
        }
        ASSERT_TRUE(keptAlive);

        // Another thread resolves it first. Its own session loads the row fresh, and the first use
        // stamps last_used, which is a write: the row is at version 2 and this thread's copy is not.
        const auto elsewhere{ std::async(std::launch::async, [&] {
                                  return authTokenService->processAuthToken("subsonic", client, "the-token").state;
                              }).get() };
        ASSERT_EQ(elsewhere, IAuthTokenService::AuthTokenProcessResult::State::Granted);

        // This thread's copy still says "never used", so it wants to stamp too -- on top of a
        // version the row has left behind.
        IAuthTokenService::AuthTokenProcessResult::State here{};
        EXPECT_NO_THROW(here = authTokenService->processAuthToken("subsonic", client, "the-token").state);
        EXPECT_EQ(here, IAuthTokenService::AuthTokenProcessResult::State::Granted);

        // And nothing is left behind to poison this thread: a write transaction that has nothing
        // to do with the token commits.
        EXPECT_NO_THROW({
            auto transaction{ session.getDb().getTLSSession().createWriteTransaction() };
        });
        EXPECT_NO_THROW(here = authTokenService->processAuthToken("subsonic", client, "the-token").state);
        EXPECT_EQ(here, IAuthTokenService::AuthTokenProcessResult::State::Granted);

        // The fixture checks that every table is empty afterwards; the user goes with its scope.
        authTokenService->clearAuthTokens("subsonic", user.getId());
    }
} // namespace lms::auth::tests
