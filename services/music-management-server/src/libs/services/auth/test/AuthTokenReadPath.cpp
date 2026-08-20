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
} // namespace lms::auth::tests
