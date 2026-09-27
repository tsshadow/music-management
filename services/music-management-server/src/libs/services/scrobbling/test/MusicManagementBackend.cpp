/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <chrono>
#include <functional>
#include <memory>
#include <thread>

#include <boost/asio/io_context.hpp>

#include <gtest/gtest.h>

#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>
#include <Wt/WDateTime.h>

#include "database/MumaListenOutbox.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackArtistLink.hpp"
#include "database/objects/User.hpp"

#include "Common.hpp"
#include "FakeHttpClient.hpp"
#include "musicmanagement/MusicManagementBackend.hpp"

namespace lms::scrobbling::musicManagement::tests
{
    namespace
    {
        using core::http::tests::FakeHttpClient;
        using core::http::tests::SentRequests;

        Wt::Json::Object parseBody(const core::http::ClientPOSTRequestParameters& request)
        {
            Wt::Json::Object body;
            Wt::Json::parse(request.message.body(), body);
            return body;
        }

        std::string headerOf(const core::http::ClientPOSTRequestParameters& request, const std::string& name)
        {
            const std::string* value{ request.message.getHeader(name) };
            return value ? *value : std::string{};
        }

        // The listen relay to MuMa's /api/scrobble/event, with the network replaced by a recorder.
        // A track with a title, an album and an artist, and the user who played it.
        class MusicManagementScrobbling : public db::tests::DatabaseFixture
        {
        protected:
            void SetUp() override
            {
                auto transaction{ session.createWriteTransaction() };
                track.get().modify()->setName("Raise Your Fist");
                track.get().modify()->setAbsoluteFilePath("/music/Angerfist/Raise Your Fist.mp3");
                track.get().modify()->setRelease(release.get());
                db::TrackArtistLink::pointer link{ session.create<db::TrackArtistLink>(track.get(), artist.get(), db::TrackArtistLinkType::Artist) };
                link.modify()->setArtistName("Angerfist");
            }

            void TearDown() override
            {
                auto transaction{ session.createWriteTransaction() };
                session.execute("DELETE FROM muma_listen_outbox");
            }

            // Retries are quick here, so a test waits milliseconds for one, not seconds.
            static ListenOutboxSettings quickRetries()
            {
                ListenOutboxSettings settings;
                settings.minRetryDelay = std::chrono::milliseconds{ 1 };
                settings.maxRetryDelay = std::chrono::milliseconds{ 4 };
                return settings;
            }

            std::unique_ptr<IScrobblingBackend> createBackend(std::string apiKey = "system-key", ListenOutboxSettings settings = quickRetries(), std::shared_ptr<SentRequests> recorder = {})
            {
                return std::make_unique<MusicManagementBackend>(ioContext, session.getDb(), std::make_unique<FakeHttpClient>(recorder ? recorder : sent), std::move(apiKey), settings);
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

            std::size_t outboxCount()
            {
                auto transaction{ session.createReadTransaction() };
                return db::mumaListenOutbox::getStatus(session).count;
            }

            TimedListen timedListenAt(std::time_t listenedAt) const
            {
                TimedListen listen;
                static_cast<Listen&>(listen) = listenOf(user.getId());
                listen.listenedAt = Wt::WDateTime::fromTime_t(listenedAt);
                return listen;
            }

            long long listenedAtOf(std::size_t index) const
            {
                return static_cast<long long>(parseBody(sent->posts.at(index)).get("listened_at"));
            }

            Listen listenOf(db::UserId userId) const
            {
                Listen listen;
                listen.userId = userId;
                listen.trackId = track.getId();
                return listen;
            }

            boost::asio::io_context ioContext;
            std::shared_ptr<SentRequests> sent{ std::make_shared<SentRequests>() };
            db::tests::ScopedArtist artist{ session, "Angerfist" };
            db::tests::ScopedRelease release{ session, "Raise Your Fist EP" };
            db::tests::ScopedTrack track{ session };
            db::tests::ScopedUser user{ session, "user" };
        };
    } // namespace

    TEST_F(MusicManagementScrobbling, aFinishedListenIsRelayedWithUserTrackAndTime)
    {
        const auto backend{ createBackend() };
        const auto before{ Wt::WDateTime::currentDateTime().toTime_t() };

        backend->listenFinished(listenOf(user.getId()), std::chrono::seconds{ 185 });

        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ parseBody(sent->posts.front()) };
        EXPECT_EQ(static_cast<std::string>(body.get("username")), "user");
        EXPECT_EQ(static_cast<std::string>(body.get("track_title")), "Raise Your Fist");
        EXPECT_EQ(static_cast<std::string>(body.get("album_name")), "Raise Your Fist EP");
        EXPECT_EQ(static_cast<std::string>(body.get("artist_name")), "Angerfist");
        EXPECT_EQ(static_cast<long long>(body.get("played_secs")), 185);
        // Nobody told the listen where it happened, so it says it came through this server.
        EXPECT_EQ(static_cast<std::string>(body.get("source")), "lms");
        const auto listenedAt{ static_cast<long long>(body.get("listened_at")) };
        EXPECT_GE(listenedAt, before);
        EXPECT_LE(listenedAt, Wt::WDateTime::currentDateTime().toTime_t());

        // MuMa matches a listen by artist and title; the file path is not part of this payload
        // (the rating relay is the one that carries it).
        EXPECT_FALSE(body.contains("path"));

        EXPECT_EQ(headerOf(sent->posts.front(), "X-API-Key"), "system-key");
        EXPECT_EQ(headerOf(sent->posts.front(), "Content-Type"), "application/json");
    }

    TEST_F(MusicManagementScrobbling, aTimedListenKeepsItsOwnTimestampSourceAndDuration)
    {
        const auto backend{ createBackend() };
        TimedListen listen;
        static_cast<Listen&>(listen) = listenOf(user.getId());
        listen.source = "auto";
        listen.playedDuration = std::chrono::seconds{ 42 };
        listen.listenedAt = Wt::WDateTime::fromTime_t(1'700'000'000);

        backend->addTimedListen(listen);

        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ parseBody(sent->posts.front()) };
        EXPECT_EQ(static_cast<long long>(body.get("listened_at")), 1'700'000'000);
        EXPECT_EQ(static_cast<std::string>(body.get("source")), "auto");
        EXPECT_EQ(static_cast<long long>(body.get("played_secs")), 42);
    }

    // The duration the client reported rides on the listen and wins over the local player's own.
    TEST_F(MusicManagementScrobbling, theClientsDurationWinsOverTheLocalOne)
    {
        const auto backend{ createBackend() };
        Listen listen{ listenOf(user.getId()) };
        listen.playedDuration = std::chrono::seconds{ 30 };

        backend->listenFinished(listen, std::chrono::seconds{ 300 });

        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        EXPECT_EQ(static_cast<long long>(parseBody(sent->posts.front()).get("played_secs")), 30);
    }

    TEST_F(MusicManagementScrobbling, noDurationMeansNoPlayedSeconds)
    {
        const auto backend{ createBackend() };

        backend->listenFinished(listenOf(user.getId()), std::chrono::seconds{ 0 });

        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        EXPECT_FALSE(parseBody(sent->posts.front()).contains("played_secs"));
    }

    // A started playback is not a listen: MuMa records every event it gets as one.
    TEST_F(MusicManagementScrobbling, aStartedListenIsNotRelayed)
    {
        const auto backend{ createBackend() };

        backend->listenStarted(listenOf(user.getId()));

        drain();

        EXPECT_TRUE(sent->posts.empty());
    }

    TEST_F(MusicManagementScrobbling, aListenOfAnUnknownUserOrTrackIsDropped)
    {
        const auto backend{ createBackend() };

        backend->listenFinished(listenOf(db::UserId{ 987654 }), std::nullopt);
        drain();

        Listen unknownTrack{ listenOf(user.getId()) };
        unknownTrack.trackId = db::TrackId{ 987654 };
        backend->listenFinished(unknownTrack, std::nullopt);
        drain();

        EXPECT_TRUE(sent->posts.empty());
    }

    TEST_F(MusicManagementScrobbling, noConfiguredKeyMeansNoKeyHeader)
    {
        const auto backend{ createBackend("") };

        backend->listenFinished(listenOf(user.getId()), std::nullopt);

        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        EXPECT_EQ(sent->posts.front().message.getHeader("X-API-Key"), nullptr);
    }

    TEST_F(MusicManagementScrobbling, withoutAClientNothingIsSentAndNothingBreaks)
    {
        MusicManagementBackend backend{ ioContext, session.getDb(), nullptr, "system-key" };
        IScrobblingBackend& asBackend{ backend };

        EXPECT_NO_THROW(asBackend.listenFinished(listenOf(user.getId()), std::nullopt));
        drain();
        EXPECT_EQ(outboxCount(), 0U);
    }

    // Recording a listen only writes the outbox; the POST goes out from the io_context, never
    // from the thread that recorded it (a Wt request thread in production).
    TEST_F(MusicManagementScrobbling, recordingAListenSendsNothingOnTheCallingThread)
    {
        const auto backend{ createBackend() };

        backend->listenFinished(listenOf(user.getId()), std::nullopt);

        EXPECT_TRUE(sent->posts.empty());
        EXPECT_EQ(outboxCount(), 1U);
        drain();
        EXPECT_EQ(sent->posts.size(), 1U);
    }

    TEST_F(MusicManagementScrobbling, aListenStaysInTheOutboxUntilMusicManagerHasIt)
    {
        const auto backend{ createBackend() };
        backend->listenFinished(listenOf(user.getId()), std::nullopt);
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        // Every status comes back to the relay, so it -- not the send queue -- decides.
        EXPECT_TRUE(sent->posts.front().treatAnyStatusAsSuccess);
        EXPECT_EQ(outboxCount(), 1U);

        answer(0, 200);
        EXPECT_EQ(outboxCount(), 0U);
        EXPECT_EQ(sent->posts.size(), 1U);
    }

    // The outage bug report 075 describes, played through: three listens made while music-manager
    // is down arrive once it is back, in the order they were made, one request at a time.
    TEST_F(MusicManagementScrobbling, anOutageThenRecoveryDeliversEveryListenInOrder)
    {
        const auto backend{ createBackend() };
        backend->addTimedListen(timedListenAt(1'700'000'000));
        backend->addTimedListen(timedListenAt(1'700'000'300));
        backend->addTimedListen(timedListenAt(1'700'000'600));
        drain();

        // One in flight, the rest wait behind it.
        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(listenedAtOf(0), 1'700'000'000);

        // Down: the connection fails, then music-manager answers 503 while it starts up.
        failTransport(0);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        EXPECT_EQ(listenedAtOf(1), 1'700'000'000);
        answer(1, 503);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 3; }));
        EXPECT_EQ(listenedAtOf(2), 1'700'000'000);
        EXPECT_EQ(outboxCount(), 3U);

        // Back.
        answer(2, 200);
        ASSERT_EQ(sent->posts.size(), 4U);
        EXPECT_EQ(listenedAtOf(3), 1'700'000'300);
        answer(3, 201);
        ASSERT_EQ(sent->posts.size(), 5U);
        EXPECT_EQ(listenedAtOf(4), 1'700'000'600);
        answer(4, 200);

        EXPECT_EQ(sent->posts.size(), 5U);
        EXPECT_EQ(outboxCount(), 0U);
    }

    // The answer can be lost after music-manager stored the listen. The retry then sends the very
    // same body -- same start time -- which music-manager's unique (username, listened_at, track)
    // absorbs, and its answer to the duplicate clears the listen here.
    TEST_F(MusicManagementScrobbling, aRetryIsTheSameListenSoADuplicateIsHarmless)
    {
        const auto backend{ createBackend() };
        backend->listenFinished(listenOf(user.getId()), std::chrono::seconds{ 185 });
        drain();

        failTransport(0);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        EXPECT_EQ(sent->posts[1].message.body(), sent->posts[0].message.body());
        EXPECT_EQ(headerOf(sent->posts[1], "X-API-Key"), "system-key");

        answer(1, 409);
        EXPECT_EQ(outboxCount(), 0U);
    }

    TEST_F(MusicManagementScrobbling, theOutboxSurvivesARestart)
    {
        {
            const auto backend{ createBackend() };
            backend->addTimedListen(timedListenAt(1'700'000'000));
            drain();
            ASSERT_EQ(sent->posts.size(), 1U);
            // LMS stops before music-manager answers.
        }
        EXPECT_EQ(outboxCount(), 1U);

        // The answer to the old process arrives nowhere, and does not remove anything.
        answer(0, 200);
        EXPECT_EQ(outboxCount(), 1U);

        const auto restarted{ std::make_shared<SentRequests>() };
        const auto backend{ createBackend("system-key", quickRetries(), restarted) };
        drain();

        ASSERT_EQ(restarted->posts.size(), 1U);
        EXPECT_EQ(restarted->posts.front().message.body(), sent->posts.front().message.body());
        answer(0, 200, restarted.get());
        EXPECT_EQ(outboxCount(), 0U);
    }

    TEST_F(MusicManagementScrobbling, beyondItsSizeTheOutboxDropsTheOldest)
    {
        ListenOutboxSettings settings{ quickRetries() };
        settings.maxCount = 2;
        const auto backend{ createBackend("system-key", settings) };

        backend->addTimedListen(timedListenAt(1'700'000'000));
        backend->addTimedListen(timedListenAt(1'700'000'300));
        backend->addTimedListen(timedListenAt(1'700'000'600));
        EXPECT_EQ(outboxCount(), 2U);
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(listenedAtOf(0), 1'700'000'300);
    }

    TEST_F(MusicManagementScrobbling, aListenPastItsAgeIsDropped)
    {
        {
            auto transaction{ session.createWriteTransaction() };
            db::mumaListenOutbox::push(session, R"({"listened_at":1})", Wt::WDateTime::currentDateTime().addSecs(-2 * 3600));
        }
        ListenOutboxSettings settings{ quickRetries() };
        settings.maxAge = std::chrono::hours{ 1 };
        const auto backend{ createBackend("system-key", settings) };
        backend->addTimedListen(timedListenAt(1'700'000'000));
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(listenedAtOf(0), 1'700'000'000);
        EXPECT_EQ(outboxCount(), 1U);
    }

    // A body music-manager rejects will be rejected every time; it must not block the ones behind it.
    TEST_F(MusicManagementScrobbling, aListenRefusedForGoodIsDroppedAndTheNextOneGoes)
    {
        const auto backend{ createBackend() };
        backend->addTimedListen(timedListenAt(1'700'000'000));
        backend->addTimedListen(timedListenAt(1'700'000'300));
        drain();

        answer(0, 422);
        ASSERT_EQ(sent->posts.size(), 2U);
        EXPECT_EQ(listenedAtOf(1), 1'700'000'300);
        EXPECT_EQ(outboxCount(), 1U);
    }

    // 401/403 is a key that is being rotated, not a listen that is wrong: it waits.
    TEST_F(MusicManagementScrobbling, anUnauthorisedAnswerKeepsTheListen)
    {
        const auto backend{ createBackend() };
        backend->listenFinished(listenOf(user.getId()), std::nullopt);
        drain();

        answer(0, 401);
        EXPECT_EQ(outboxCount(), 1U);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        answer(1, 200);
        EXPECT_EQ(outboxCount(), 0U);
    }

    // A listen recorded while a retry is pending waits for that retry instead of jumping ahead.
    TEST_F(MusicManagementScrobbling, aNewListenDuringAnOutageWaitsItsTurn)
    {
        const auto backend{ createBackend() };
        backend->addTimedListen(timedListenAt(1'700'000'000));
        drain();
        failTransport(0);

        backend->addTimedListen(timedListenAt(1'700'000'300));
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        EXPECT_EQ(listenedAtOf(1), 1'700'000'000);
        answer(1, 200);
        ASSERT_EQ(sent->posts.size(), 3U);
        EXPECT_EQ(listenedAtOf(2), 1'700'000'300);
        answer(2, 200);
        EXPECT_EQ(outboxCount(), 0U);
    }
} // namespace lms::scrobbling::musicManagement::tests
