/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <chrono>
#include <functional>
#include <memory>
#include <string>
#include <thread>

#include <boost/asio/io_context.hpp>

#include <gtest/gtest.h>

#include <Wt/WDateTime.h>

#include "database/MumaListenOutbox.hpp"
#include "database/MumaRatingOutbox.hpp"
#include "services/mumaoutbox/IMumaOutboxRelay.hpp"

#include "Common.hpp"
#include "FakeHttpClient.hpp"

namespace lms::mumaOutbox::tests
{
    namespace
    {
        using core::http::tests::FakeHttpClient;
        using core::http::tests::SentRequests;

        std::string headerOf(const core::http::ClientPOSTRequestParameters& request, const std::string& name)
        {
            const std::string* value{ request.message.getHeader(name) };
            return value ? *value : std::string{};
        }

        std::string listenAt(long long listenedAt)
        {
            return R"({"listened_at":)" + std::to_string(listenedAt) + "}";
        }

        std::string ratingOf(const std::string& objectId, int rating)
        {
            return R"({"event":"rating_changed","object_type":"track","object_id":")" + objectId + R"(","rating":)" + std::to_string(rating) + "}";
        }

        RatingKey trackKey(const std::string& objectId)
        {
            return RatingKey{ .username = "user", .objectType = "track", .objectId = objectId };
        }

        // The relay over both outboxes, with the network replaced by a recorder and a real
        // database underneath.
        class MumaOutboxRelayTest : public db::tests::DatabaseFixture
        {
        protected:
            void TearDown() override
            {
                auto transaction{ session.createWriteTransaction() };
                session.execute("DELETE FROM muma_listen_outbox");
                session.execute("DELETE FROM muma_rating_outbox");
            }

            // Retries are quick here, so a test waits milliseconds for one, not seconds.
            static MumaOutboxSettings quickRetries()
            {
                MumaOutboxSettings settings;
                settings.minRetryDelay = std::chrono::milliseconds{ 1 };
                settings.maxRetryDelay = std::chrono::milliseconds{ 4 };
                return settings;
            }

            std::unique_ptr<IMumaOutboxRelay> createRelay(MumaOutboxSettings settings = quickRetries(), std::shared_ptr<SentRequests> recorder = {}, std::string apiKey = "system-key")
            {
                return createMumaOutboxRelay(ioContext, session.getDb(), std::make_unique<FakeHttpClient>(recorder ? recorder : sent), std::move(apiKey), settings);
            }

            // Runs whatever the relay has posted to the io_context so far, on this thread.
            void drain()
            {
                ioContext.restart();
                ioContext.poll();
            }

            // Drains until `done` holds, for at most two seconds: long enough for any retry timer here.
            bool drainUntil(const std::function<bool()>& done)
            {
                const auto deadline{ std::chrono::steady_clock::now() + std::chrono::seconds{ 2 } };
                while (std::chrono::steady_clock::now() < deadline)
                {
                    drain();
                    if (done())
                        return true;
                    std::this_thread::sleep_for(std::chrono::milliseconds{ 1 });
                }
                return false;
            }

            // Plays music-manager's answer to the `index`th POST back through its own callback.
            void answer(std::size_t index, int status, SentRequests* recorder = nullptr)
            {
                Wt::Http::Message msg;
                msg.setStatus(status);
                (recorder ? recorder : sent.get())->posts.at(index).onSuccessFunc(msg);
                drain();
            }

            // The connection failed: what the send queue reports once its own retries are spent.
            void failTransport(std::size_t index)
            {
                sent->posts.at(index).onFailureFunc();
                drain();
            }

            std::size_t listenCount()
            {
                auto transaction{ session.createReadTransaction() };
                return db::mumaListenOutbox::getStatus(session).count;
            }

            std::size_t ratingCount()
            {
                auto transaction{ session.createReadTransaction() };
                return db::mumaRatingOutbox::getStatus(session).count;
            }

            // A row a previous run of LMS left, queued `ageSeconds` ago.
            void leaveListen(const std::string& payload, int ageSeconds)
            {
                auto transaction{ session.createWriteTransaction() };
                db::mumaListenOutbox::push(session, payload, Wt::WDateTime::currentDateTime().addSecs(-ageSeconds));
            }

            void leaveRating(const RatingKey& key, const std::string& payload, int ageSeconds)
            {
                auto transaction{ session.createWriteTransaction() };
                db::mumaRatingOutbox::replace(session, key, payload, Wt::WDateTime::currentDateTime().addSecs(-ageSeconds));
            }

            std::string bodyOf(std::size_t index) const { return sent->posts.at(index).message.body(); }
            std::string urlOf(std::size_t index) const { return sent->posts.at(index).relativeUrl; }

            boost::asio::io_context ioContext;
            std::shared_ptr<SentRequests> sent{ std::make_shared<SentRequests>() };
        };
    } // namespace

    // Queueing only writes the outbox; the POST goes out from the io_context, never from the
    // thread that queued it (a Wt request thread in production).
    TEST_F(MumaOutboxRelayTest, enqueueingSendsNothingOnTheCallingThread)
    {
        const auto relay{ createRelay() };

        relay->enqueueListen(listenAt(1'700'000'000));
        relay->enqueueRating(trackKey("12"), ratingOf("12", 4));

        EXPECT_TRUE(sent->posts.empty());
        EXPECT_EQ(listenCount(), 1U);
        EXPECT_EQ(ratingCount(), 1U);
        drain();
        EXPECT_EQ(sent->posts.size(), 1U);
    }

    TEST_F(MumaOutboxRelayTest, aListenStaysInTheOutboxUntilMusicManagerHasIt)
    {
        const auto relay{ createRelay() };
        relay->enqueueListen(listenAt(1'700'000'000));
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        // Every status comes back to the relay, so it -- not the send queue -- decides.
        EXPECT_TRUE(sent->posts.front().treatAnyStatusAsSuccess);
        EXPECT_EQ(headerOf(sent->posts.front(), "X-API-Key"), "system-key");
        EXPECT_EQ(headerOf(sent->posts.front(), "Content-Type"), "application/json");
        EXPECT_EQ(listenCount(), 1U);

        answer(0, 200);
        EXPECT_EQ(listenCount(), 0U);
        EXPECT_EQ(sent->posts.size(), 1U);
    }

    TEST_F(MumaOutboxRelayTest, noConfiguredKeyMeansNoKeyHeader)
    {
        const auto relay{ createRelay(quickRetries(), {}, "") };
        relay->enqueueListen(listenAt(1'700'000'000));
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(sent->posts.front().message.getHeader("X-API-Key"), nullptr);
    }

    // The outage bug report 075 describes, played through: three listens made while music-manager
    // is down arrive once it is back, in the order they were made, one request at a time.
    TEST_F(MumaOutboxRelayTest, anOutageThenRecoveryDeliversEveryListenInOrder)
    {
        const auto relay{ createRelay() };
        relay->enqueueListen(listenAt(1'700'000'000));
        relay->enqueueListen(listenAt(1'700'000'300));
        relay->enqueueListen(listenAt(1'700'000'600));
        drain();

        // One in flight, the rest wait behind it.
        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(bodyOf(0), listenAt(1'700'000'000));

        // Down: the connection fails, then music-manager answers 503 while it starts up.
        failTransport(0);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        EXPECT_EQ(bodyOf(1), listenAt(1'700'000'000));
        answer(1, 503);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 3; }));
        EXPECT_EQ(bodyOf(2), listenAt(1'700'000'000));
        EXPECT_EQ(listenCount(), 3U);

        // Back.
        answer(2, 200);
        ASSERT_EQ(sent->posts.size(), 4U);
        EXPECT_EQ(bodyOf(3), listenAt(1'700'000'300));
        answer(3, 201);
        ASSERT_EQ(sent->posts.size(), 5U);
        EXPECT_EQ(bodyOf(4), listenAt(1'700'000'600));
        answer(4, 200);

        EXPECT_EQ(sent->posts.size(), 5U);
        EXPECT_EQ(listenCount(), 0U);
    }

    // The answer can be lost after music-manager stored the listen. The retry then sends the very
    // same body, which music-manager absorbs, and its answer to the duplicate clears the row.
    TEST_F(MumaOutboxRelayTest, aRetryIsTheSameListenSoADuplicateIsHarmless)
    {
        const auto relay{ createRelay() };
        relay->enqueueListen(listenAt(1'700'000'000));
        drain();

        failTransport(0);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        EXPECT_EQ(bodyOf(1), bodyOf(0));
        EXPECT_EQ(headerOf(sent->posts[1], "X-API-Key"), "system-key");

        answer(1, 409);
        EXPECT_EQ(listenCount(), 0U);
    }

    TEST_F(MumaOutboxRelayTest, theOutboxSurvivesARestart)
    {
        {
            const auto relay{ createRelay() };
            relay->enqueueListen(listenAt(1'700'000'000));
            drain();
            ASSERT_EQ(sent->posts.size(), 1U);
            // LMS stops before music-manager answers.
        }
        EXPECT_EQ(listenCount(), 1U);

        // The answer to the old process arrives nowhere, and does not remove anything.
        answer(0, 200);
        EXPECT_EQ(listenCount(), 1U);

        const auto restarted{ std::make_shared<SentRequests>() };
        const auto relay{ createRelay(quickRetries(), restarted) };
        relay->start();
        drain();

        ASSERT_EQ(restarted->posts.size(), 1U);
        EXPECT_EQ(restarted->posts.front().message.body(), bodyOf(0));
        answer(0, 200, restarted.get());
        EXPECT_EQ(listenCount(), 0U);
    }

    TEST_F(MumaOutboxRelayTest, beyondItsSizeTheListenOutboxDropsTheOldest)
    {
        MumaOutboxSettings settings{ quickRetries() };
        settings.listenMaxCount = 2;
        const auto relay{ createRelay(settings) };

        relay->enqueueListen(listenAt(1'700'000'000));
        relay->enqueueListen(listenAt(1'700'000'300));
        relay->enqueueListen(listenAt(1'700'000'600));
        EXPECT_EQ(listenCount(), 2U);
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(bodyOf(0), listenAt(1'700'000'300));
    }

    TEST_F(MumaOutboxRelayTest, aListenPastItsAgeIsDropped)
    {
        leaveListen(listenAt(1), 2 * 3600);
        MumaOutboxSettings settings{ quickRetries() };
        settings.listenMaxAge = std::chrono::hours{ 1 };
        const auto relay{ createRelay(settings) };
        relay->enqueueListen(listenAt(1'700'000'000));
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(bodyOf(0), listenAt(1'700'000'000));
        EXPECT_EQ(listenCount(), 1U);
    }

    // A body music-manager rejects will be rejected every time; it must not block the ones behind it.
    TEST_F(MumaOutboxRelayTest, aListenRefusedForGoodIsDroppedAndTheNextOneGoes)
    {
        const auto relay{ createRelay() };
        relay->enqueueListen(listenAt(1'700'000'000));
        relay->enqueueListen(listenAt(1'700'000'300));
        drain();

        answer(0, 422);
        ASSERT_EQ(sent->posts.size(), 2U);
        EXPECT_EQ(bodyOf(1), listenAt(1'700'000'300));
        EXPECT_EQ(listenCount(), 1U);
    }

    // 401/403 is a key that is being rotated, not a listen that is wrong: it waits.
    TEST_F(MumaOutboxRelayTest, anUnauthorisedAnswerKeepsTheListen)
    {
        const auto relay{ createRelay() };
        relay->enqueueListen(listenAt(1'700'000'000));
        drain();

        answer(0, 401);
        EXPECT_EQ(listenCount(), 1U);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        answer(1, 200);
        EXPECT_EQ(listenCount(), 0U);
    }

    // A listen recorded while a retry is pending waits for that retry instead of jumping ahead.
    TEST_F(MumaOutboxRelayTest, aNewListenDuringAnOutageWaitsItsTurn)
    {
        const auto relay{ createRelay() };
        relay->enqueueListen(listenAt(1'700'000'000));
        drain();
        failTransport(0);

        relay->enqueueListen(listenAt(1'700'000'300));
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        EXPECT_EQ(bodyOf(1), listenAt(1'700'000'000));
        answer(1, 200);
        ASSERT_EQ(sent->posts.size(), 3U);
        EXPECT_EQ(bodyOf(2), listenAt(1'700'000'300));
        answer(2, 200);
        EXPECT_EQ(listenCount(), 0U);
    }

    // Oldest first across the two tables, whichever table that is.
    TEST_F(MumaOutboxRelayTest, theOlderChangeGoesFirstAcrossTables)
    {
        leaveListen(listenAt(1'700'000'000), 100);
        leaveRating(trackKey("12"), ratingOf("12", 4), 50);
        {
            const auto relay{ createRelay() };
            relay->start();
            drain();
            ASSERT_EQ(sent->posts.size(), 1U);
            EXPECT_EQ(bodyOf(0), listenAt(1'700'000'000));
            answer(0, 200);
            ASSERT_EQ(sent->posts.size(), 2U);
            EXPECT_EQ(bodyOf(1), ratingOf("12", 4));
            answer(1, 200);
        }
        EXPECT_EQ(listenCount() + ratingCount(), 0U);

        // And the reverse.
        leaveRating(trackKey("13"), ratingOf("13", 2), 100);
        leaveListen(listenAt(1'700'000'300), 50);
        const auto relay{ createRelay() };
        relay->start();
        drain();
        ASSERT_EQ(sent->posts.size(), 3U);
        EXPECT_EQ(bodyOf(2), ratingOf("13", 2));
        answer(2, 200);
        ASSERT_EQ(sent->posts.size(), 4U);
        EXPECT_EQ(bodyOf(3), listenAt(1'700'000'300));
        answer(3, 200);
    }

    TEST_F(MumaOutboxRelayTest, eachTableGoesToItsOwnUrl)
    {
        leaveListen(listenAt(1'700'000'000), 100);
        leaveRating(trackKey("12"), ratingOf("12", 4), 50);
        const auto relay{ createRelay() };
        relay->start();
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(urlOf(0), "/scrobble/event");
        answer(0, 200);
        ASSERT_EQ(sent->posts.size(), 2U);
        EXPECT_EQ(urlOf(1), "/rating/lms-event");
        EXPECT_EQ(headerOf(sent->posts[1], "X-API-Key"), "system-key");
        answer(1, 200);
    }

    // The two tables number their rows on their own, so an id says nothing without its table.
    TEST_F(MumaOutboxRelayTest, anAnswerRemovesTheRowFromItsOwnTable)
    {
        const long long created{ Wt::WDateTime::currentDateTime().toTime_t() };
        {
            auto transaction{ session.createWriteTransaction() };
            session.execute("INSERT INTO muma_listen_outbox (id, payload, created) VALUES (5000, '" + listenAt(1'700'000'000) + "', " + std::to_string(created - 100) + ")");
            session.execute("INSERT INTO muma_rating_outbox (id, username, object_type, object_id, payload, created) VALUES (5000, 'user', 'track', '12', '" + ratingOf("12", 4) + "', " + std::to_string(created - 50) + ")");
        }
        const auto relay{ createRelay() };
        relay->start();
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(urlOf(0), "/scrobble/event");
        answer(0, 200);
        EXPECT_EQ(listenCount(), 0U);
        EXPECT_EQ(ratingCount(), 1U);

        ASSERT_EQ(sent->posts.size(), 2U);
        EXPECT_EQ(urlOf(1), "/rating/lms-event");
        answer(1, 200);
        EXPECT_EQ(ratingCount(), 0U);
    }

    // The same music-manager serves both routes, so a failed rating holds back the next listen.
    TEST_F(MumaOutboxRelayTest, oneBackoffForBoth)
    {
        MumaOutboxSettings settings;
        settings.minRetryDelay = std::chrono::hours{ 1 };
        settings.maxRetryDelay = std::chrono::hours{ 1 };
        const auto relay{ createRelay(settings) };
        relay->enqueueRating(trackKey("12"), ratingOf("12", 4));
        drain();
        ASSERT_EQ(sent->posts.size(), 1U);

        failTransport(0);
        relay->enqueueListen(listenAt(1'700'000'000));
        drain();

        EXPECT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(listenCount(), 1U);
        EXPECT_EQ(ratingCount(), 1U);
    }

    // Without music-management-url there is no relay at all, and the producers check for that.
    TEST_F(MumaOutboxRelayTest, aRelayWithoutAClientSendsNothingAndKeepsTheRows)
    {
        const auto relay{ createMumaOutboxRelay(ioContext, session.getDb(), nullptr, "system-key", quickRetries()) };
        relay->enqueueListen(listenAt(1'700'000'000));
        EXPECT_NO_THROW(drain());
        EXPECT_EQ(listenCount(), 1U);
    }
} // namespace lms::mumaOutbox::tests
