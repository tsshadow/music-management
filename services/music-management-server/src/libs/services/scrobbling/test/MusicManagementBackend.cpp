/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <memory>

#include <gtest/gtest.h>

#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>
#include <Wt/WDateTime.h>

#include "database/objects/Artist.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackArtistLink.hpp"
#include "database/objects/User.hpp"

#include "Common.hpp"
#include "FakeHttpClient.hpp"
#include "http/RetryPolicy.hpp"
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

            std::unique_ptr<IScrobblingBackend> createBackend(std::string apiKey = "system-key")
            {
                return std::make_unique<MusicManagementBackend>(session.getDb(), std::make_unique<FakeHttpClient>(sent), std::move(apiKey));
            }

            Listen listenOf(db::UserId userId) const
            {
                Listen listen;
                listen.userId = userId;
                listen.trackId = track.getId();
                return listen;
            }

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

        ASSERT_EQ(sent->posts.size(), 1);
        EXPECT_EQ(static_cast<long long>(parseBody(sent->posts.front()).get("played_secs")), 30);
    }

    TEST_F(MusicManagementScrobbling, noDurationMeansNoPlayedSeconds)
    {
        const auto backend{ createBackend() };

        backend->listenFinished(listenOf(user.getId()), std::chrono::seconds{ 0 });

        ASSERT_EQ(sent->posts.size(), 1);
        EXPECT_FALSE(parseBody(sent->posts.front()).contains("played_secs"));
    }

    // A started playback is not a listen: MuMa records every event it gets as one.
    TEST_F(MusicManagementScrobbling, aStartedListenIsNotRelayed)
    {
        const auto backend{ createBackend() };

        backend->listenStarted(listenOf(user.getId()));

        EXPECT_TRUE(sent->posts.empty());
    }

    TEST_F(MusicManagementScrobbling, aListenOfAnUnknownUserOrTrackIsDropped)
    {
        const auto backend{ createBackend() };

        backend->listenFinished(listenOf(db::UserId{ 987654 }), std::nullopt);
        Listen unknownTrack{ listenOf(user.getId()) };
        unknownTrack.trackId = db::TrackId{ 987654 };
        backend->listenFinished(unknownTrack, std::nullopt);

        EXPECT_TRUE(sent->posts.empty());
    }

    TEST_F(MusicManagementScrobbling, noConfiguredKeyMeansNoKeyHeader)
    {
        const auto backend{ createBackend("") };

        backend->listenFinished(listenOf(user.getId()), std::nullopt);

        ASSERT_EQ(sent->posts.size(), 1);
        EXPECT_EQ(sent->posts.front().message.getHeader("X-API-Key"), nullptr);
    }

    TEST_F(MusicManagementScrobbling, withoutAClientNothingIsSentAndNothingBreaks)
    {
        MusicManagementBackend backend{ session.getDb(), nullptr, "system-key" };
        IScrobblingBackend& asBackend{ backend };

        EXPECT_NO_THROW(asBackend.listenFinished(listenOf(user.getId()), std::nullopt));
    }

    // Pins how the send queue treats a relayed listen, as it is today. The request is a plain one:
    // not a proxy call, no callbacks. So a transport error is retried until the queue's retry cap
    // and then the listen is dropped; a 429 is retried later, a bounded number of times; and any
    // other non-200 answer is dropped at once (SendQueue calls the absent onFailureFunc). A listen
    // MuMa never received is gone -- nothing re-sends it later.
    TEST_F(MusicManagementScrobbling, aRelayedListenIsRetriedThenDroppedByTheQueue)
    {
        const auto backend{ createBackend() };
        backend->listenFinished(listenOf(user.getId()), std::nullopt);

        ASSERT_EQ(sent->posts.size(), 1);
        const core::http::ClientPOSTRequestParameters& request{ sent->posts.front() };
        EXPECT_FALSE(request.treatAnyStatusAsSuccess);
        EXPECT_EQ(request.priority, core::http::ClientRequestParameters::Priority::Normal);
        EXPECT_FALSE(request.onSuccessFunc);
        EXPECT_FALSE(request.onFailureFunc);
        EXPECT_FALSE(request.onAbortFunc);

        constexpr std::size_t maxRetries{ 2 };
        EXPECT_TRUE(core::http::decideAfterTransportError(0, maxRetries, 1, 3).retryRequest);
        EXPECT_FALSE(core::http::decideAfterTransportError(maxRetries, maxRetries, 1, 3).retryRequest);
        EXPECT_EQ(core::http::decideAfterRateLimited(request.treatAnyStatusAsSuccess, 0, 3), core::http::RateLimitedAction::RetryLater);
        EXPECT_EQ(core::http::decideAfterRateLimited(request.treatAnyStatusAsSuccess, 3, 3), core::http::RateLimitedAction::GiveUp);
    }
} // namespace lms::scrobbling::musicManagement::tests
