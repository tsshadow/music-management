/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <algorithm>
#include <chrono>
#include <functional>
#include <memory>
#include <string>
#include <thread>

#include <boost/asio/io_context.hpp>

#include <gtest/gtest.h>

#include <Wt/Http/Message.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>
#include <Wt/WDateTime.h>

#include "database/MumaRatingOutbox.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/RatedArtist.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"
#include "services/mumaoutbox/IMumaOutboxRelay.hpp"

#include "CapturingLogger.hpp"
#include "Common.hpp"
#include "FakeHttpClient.hpp"
#include "musicmanagement/MusicManagementBackend.hpp"

namespace lms::feedback::musicManagement::tests
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

        RatingRemovedEvent removalOf(const std::string& objectId)
        {
            return RatingRemovedEvent{ .objectType = "track", .objectId = objectId, .username = "user", .path = "/music/a.mp3", .previousRating = 3 };
        }

        // The rating relay to MuMa's /api/rating/lms-event: the backend on a relay of its own,
        // with the network replaced by a recorder and a real database underneath.
        class MusicManagementFeedback : public db::tests::DatabaseFixture
        {
        protected:
            void SetUp() override
            {
                auto transaction{ session.createWriteTransaction() };
                track.get().modify()->setAbsoluteFilePath("/music/Angerfist/Raise Your Fist.mp3");
            }

            void TearDown() override
            {
                backend.reset();
                relay.reset();
                removeTrackRating();
                {
                    auto transaction{ session.createWriteTransaction() };
                    session.execute("DELETE FROM muma_rating_outbox");
                }
                lms::feedback::tests::CapturingLogger::clearWarnings();
            }

            // Retries are quick here, so a test waits milliseconds for one, not seconds.
            static mumaOutbox::MumaOutboxSettings quickRetries()
            {
                mumaOutbox::MumaOutboxSettings settings;
                settings.minRetryDelay = std::chrono::milliseconds{ 1 };
                settings.maxRetryDelay = std::chrono::milliseconds{ 4 };
                return settings;
            }

            // A new relay and backend, as after a start of LMS. The relay resumes what the outbox
            // holds, as main.cpp has it do once every producer exists.
            void start(mumaOutbox::MumaOutboxSettings settings = quickRetries(), std::shared_ptr<SentRequests> recorder = {})
            {
                backend.reset();
                relay = mumaOutbox::createMumaOutboxRelay(ioContext, session.getDb(), std::make_unique<FakeHttpClient>(recorder ? recorder : sent), "system-key", settings);
                backend = std::make_unique<MusicManagementBackend>(session.getDb(), relay.get());
                relay->start();
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

            // The user rates the fixture track `rating`, through the backend as FeedbackService
            // does after its write transaction.
            void rateTrack(int rating)
            {
                db::RatedTrackId ratedTrackId;
                {
                    auto transaction{ session.createWriteTransaction() };
                    db::RatedTrack::pointer rated{ db::RatedTrack::find(session, track.getId(), user.getId()) };
                    if (!rated)
                        rated = session.create<db::RatedTrack>(track.get(), user.getId());
                    rated.modify()->setRating(rating);
                    ratedTrackId = rated->getId();
                }
                backend->onRatingChanged(ratedTrackId);
            }

            // The user clears the fixture track's rating.
            void clearTrackRating()
            {
                removeTrackRating();
                backend->onRatingRemoved(removalOf(track.getId().toString()));
            }

            std::size_t outboxCount()
            {
                auto transaction{ session.createReadTransaction() };
                return db::mumaRatingOutbox::getStatus(session).count;
            }

            Wt::Json::Object bodyOf(std::size_t index) const { return parseBody(sent->posts.at(index)); }

            void removeTrackRating()
            {
                auto transaction{ session.createWriteTransaction() };
                if (db::RatedTrack::pointer rated{ db::RatedTrack::find(session, track.getId(), user.getId()) })
                    rated.remove();
            }

            boost::asio::io_context ioContext;
            std::shared_ptr<SentRequests> sent{ std::make_shared<SentRequests>() };
            std::unique_ptr<mumaOutbox::IMumaOutboxRelay> relay;
            std::unique_ptr<IFeedbackBackend> backend;
            db::tests::ScopedTrack track{ session };
            db::tests::ScopedArtist artist{ session, "Angerfist" };
            db::tests::ScopedUser user{ session, "user" };
        };
    } // namespace

    // MuMa finds the track by its path (the LMS id means nothing there), so the path is the load-
    // bearing field of a track rating.
    TEST_F(MusicManagementFeedback, aTrackRatingCarriesUserRatingAndPath)
    {
        start();
        rateTrack(4);
        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ bodyOf(0) };
        EXPECT_EQ(static_cast<std::string>(body.get("event")), "rating_changed");
        EXPECT_EQ(static_cast<std::string>(body.get("object_type")), "track");
        EXPECT_EQ(static_cast<std::string>(body.get("object_id")), track.getId().toString());
        EXPECT_EQ(static_cast<std::string>(body.get("username")), "user");
        EXPECT_EQ(static_cast<int>(body.get("rating")), 4);
        EXPECT_EQ(static_cast<std::string>(body.get("path")), "/music/Angerfist/Raise Your Fist.mp3");
        EXPECT_EQ(sent->posts.front().relativeUrl, "/rating/lms-event");
        const std::string* key{ sent->posts.front().message.getHeader("X-API-Key") };
        ASSERT_NE(key, nullptr);
        EXPECT_EQ(*key, "system-key");
    }

    TEST_F(MusicManagementFeedback, anArtistRatingIsNamedAndHasNoPath)
    {
        start();
        db::RatedArtistId ratedArtistId;
        {
            auto transaction{ session.createWriteTransaction() };
            db::RatedArtist::pointer rated{ session.create<db::RatedArtist>(artist.get(), user.getId()) };
            rated.modify()->setRating(5);
            ratedArtistId = rated->getId();
        }

        backend->onRatingChanged(ratedArtistId);
        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ bodyOf(0) };
        EXPECT_EQ(static_cast<std::string>(body.get("object_type")), "artist");
        EXPECT_EQ(static_cast<std::string>(body.get("object_id")), "Angerfist");
        EXPECT_EQ(static_cast<int>(body.get("rating")), 5);
        EXPECT_FALSE(body.contains("path"));

        {
            auto transaction{ session.createWriteTransaction() };
            db::RatedArtist::find(session, ratedArtistId).remove();
        }
    }

    TEST_F(MusicManagementFeedback, aRemovedRatingIsReportedAsZeroWithItsPath)
    {
        start();
        backend->onRatingRemoved(removalOf("12"));
        drain();

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ bodyOf(0) };
        EXPECT_EQ(static_cast<std::string>(body.get("event")), "rating_removed");
        EXPECT_EQ(static_cast<int>(body.get("rating")), 0);
        EXPECT_EQ(static_cast<std::string>(body.get("path")), "/music/a.mp3");
    }

    TEST_F(MusicManagementFeedback, aRatingThatNoLongerExistsSendsNothing)
    {
        start();
        backend->onRatingChanged(db::RatedTrackId{ 987654 });
        backend->onRatingChanged(db::RatedArtistId{ 987654 });
        drain();

        EXPECT_TRUE(sent->posts.empty());
        EXPECT_EQ(outboxCount(), 0U);
    }

    // Stars are not mirrored to MuMa at all; only ratings are.
    TEST_F(MusicManagementFeedback, starsAreNotRelayed)
    {
        start();
        backend->onStarred(db::StarredTrackId{ 1 });
        backend->onUnstarred(db::StarredTrackId{ 1 });
        backend->onStarred(db::StarredArtistId{ 1 });
        backend->onStarred(db::StarredReleaseId{ 1 });
        drain();

        EXPECT_TRUE(sent->posts.empty());
    }

    TEST_F(MusicManagementFeedback, withoutARelayNothingIsQueuedAndNothingBreaks)
    {
        MusicManagementBackend withoutRelay{ session.getDb(), nullptr };
        IFeedbackBackend& asBackend{ withoutRelay };

        EXPECT_NO_THROW(asBackend.onRatingRemoved(removalOf("12")));
        drain();
        EXPECT_EQ(outboxCount(), 0U);
    }

    // Setting a rating only writes the outbox; the POST goes out from the io_context, never from
    // the thread that set it (a Wt request thread in production).
    TEST_F(MusicManagementFeedback, settingARatingSendsNothingOnTheCallingThread)
    {
        start();
        rateTrack(4);

        EXPECT_TRUE(sent->posts.empty());
        EXPECT_EQ(outboxCount(), 1U);
        drain();
        EXPECT_EQ(sent->posts.size(), 1U);
        // Every status comes back to the relay, so it -- not the send queue -- decides.
        EXPECT_TRUE(sent->posts.front().treatAnyStatusAsSuccess);
    }

    TEST_F(MusicManagementFeedback, anOutageThenRecoveryDeliversTheRating)
    {
        start();
        rateTrack(4);
        drain();
        ASSERT_EQ(sent->posts.size(), 1U);

        failTransport(0);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        answer(1, 503);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 3; }));
        EXPECT_EQ(outboxCount(), 1U);

        answer(2, 200);
        EXPECT_EQ(outboxCount(), 0U);
        EXPECT_EQ(sent->posts.size(), 3U);
        EXPECT_EQ(static_cast<int>(bodyOf(2).get("rating")), 4);
    }

    // Rated 3, then 5, while music-manager is down: music-manager gets 5, and never 3.
    TEST_F(MusicManagementFeedback, theLastStateWins)
    {
        start();
        rateTrack(3);
        rateTrack(5);
        EXPECT_EQ(outboxCount(), 1U);
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(static_cast<int>(bodyOf(0).get("rating")), 5);
        answer(0, 200);
        EXPECT_EQ(outboxCount(), 0U);
        EXPECT_EQ(sent->posts.size(), 1U);
    }

    // Set 4, then cleared: music-manager gets the removal, which also clears a 4 it had before.
    TEST_F(MusicManagementFeedback, aRemovalAfterASetSendsTheRemoval)
    {
        start();
        rateTrack(4);
        clearTrackRating();
        EXPECT_EQ(outboxCount(), 1U);
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(static_cast<std::string>(bodyOf(0).get("event")), "rating_removed");
        answer(0, 200);
        EXPECT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(outboxCount(), 0U);
    }

    // Rated 3, and 4 before music-manager answered about the 3: the answer about the 3 leaves the
    // row for 4 alone, which goes next.
    TEST_F(MusicManagementFeedback, aChangeDuringAnInFlightRequestIsSentAfterIt)
    {
        start();
        rateTrack(3);
        drain();
        ASSERT_EQ(sent->posts.size(), 1U);

        rateTrack(4);
        drain();
        EXPECT_EQ(sent->posts.size(), 1U);

        answer(0, 200);
        EXPECT_EQ(outboxCount(), 1U);
        ASSERT_EQ(sent->posts.size(), 2U);
        EXPECT_EQ(static_cast<int>(bodyOf(1).get("rating")), 4);
        answer(1, 200);
        EXPECT_EQ(outboxCount(), 0U);
    }

    TEST_F(MusicManagementFeedback, aRetryIsTheSameBody)
    {
        start();
        rateTrack(4);
        drain();

        failTransport(0);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        EXPECT_EQ(sent->posts[1].message.body(), sent->posts[0].message.body());
        answer(1, 200);
        EXPECT_EQ(outboxCount(), 0U);
    }

    // A body music-manager rejects will be rejected every time; it must not block the ones behind it.
    TEST_F(MusicManagementFeedback, aRefusedRatingIsDroppedAndTheNextGoes)
    {
        start();
        backend->onRatingRemoved(removalOf("12"));
        backend->onRatingRemoved(removalOf("13"));
        drain();

        answer(0, 422);
        ASSERT_EQ(sent->posts.size(), 2U);
        EXPECT_EQ(static_cast<std::string>(bodyOf(1).get("object_id")), "13");
        EXPECT_EQ(outboxCount(), 1U);
        answer(1, 200);

        const auto warnings{ lms::feedback::tests::CapturingLogger::warnings() };
        EXPECT_TRUE(std::ranges::any_of(warnings, [](const std::string& line) { return line.find("track '12' by user") != std::string::npos && line.find("HTTP 422") != std::string::npos; }));
    }

    // 403 is a key that is being rotated, not a rating that is wrong: it waits.
    TEST_F(MusicManagementFeedback, anUnauthorisedAnswerKeepsTheRating)
    {
        start();
        backend->onRatingRemoved(removalOf("12"));
        drain();

        answer(0, 403);
        EXPECT_EQ(outboxCount(), 1U);
        ASSERT_TRUE(drainUntil([&] { return sent->posts.size() == 2; }));
        answer(1, 200);
        EXPECT_EQ(outboxCount(), 0U);
    }

    TEST_F(MusicManagementFeedback, theRatingOutboxSurvivesARestart)
    {
        start();
        backend->onRatingRemoved(removalOf("12"));
        drain();
        ASSERT_EQ(sent->posts.size(), 1U);

        // LMS stops before music-manager answers, and starts again.
        const auto restarted{ std::make_shared<SentRequests>() };
        start(quickRetries(), restarted);
        // The answer to the old process arrives nowhere, and does not remove anything.
        answer(0, 200);
        EXPECT_EQ(outboxCount(), 1U);
        drain();

        ASSERT_EQ(restarted->posts.size(), 1U);
        EXPECT_EQ(restarted->posts.front().message.body(), sent->posts.front().message.body());
        answer(0, 200, restarted.get());
        EXPECT_EQ(outboxCount(), 0U);
    }

    // Nothing else sends a dropped rating again, so the WARNING names it.
    TEST_F(MusicManagementFeedback, aRatingPastItsAgeIsDroppedWithItsKeyInTheLog)
    {
        {
            auto transaction{ session.createWriteTransaction() };
            db::mumaRatingOutbox::replace(session, mumaOutbox::RatingKey{ .username = "user", .objectType = "release", .objectId = "Raise Your Fist EP" }, R"({"event":"rating_changed"})", Wt::WDateTime::currentDateTime().addSecs(-2 * 3600));
        }
        mumaOutbox::MumaOutboxSettings settings{ quickRetries() };
        settings.ratingMaxAge = std::chrono::hours{ 1 };
        start(settings);
        backend->onRatingRemoved(removalOf("12"));
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(static_cast<std::string>(bodyOf(0).get("object_id")), "12");
        EXPECT_EQ(outboxCount(), 1U);
        const auto warnings{ lms::feedback::tests::CapturingLogger::warnings() };
        EXPECT_TRUE(std::ranges::any_of(warnings, [](const std::string& line) { return line.find("rating of release 'Raise Your Fist EP' by user") != std::string::npos && line.find("restore_lms_ratings.py") != std::string::npos; }));
    }

    TEST_F(MusicManagementFeedback, beyondItsSizeTheRatingOutboxDropsTheOldest)
    {
        mumaOutbox::MumaOutboxSettings settings{ quickRetries() };
        settings.ratingMaxCount = 2;
        start(settings);

        backend->onRatingRemoved(removalOf("12"));
        backend->onRatingRemoved(removalOf("13"));
        backend->onRatingRemoved(removalOf("14"));
        EXPECT_EQ(outboxCount(), 2U);
        drain();

        ASSERT_EQ(sent->posts.size(), 1U);
        EXPECT_EQ(static_cast<std::string>(bodyOf(0).get("object_id")), "13");
        const auto warnings{ lms::feedback::tests::CapturingLogger::warnings() };
        EXPECT_TRUE(std::ranges::any_of(warnings, [](const std::string& line) { return line.find("rating of track '12' by user") != std::string::npos; }));
    }
} // namespace lms::feedback::musicManagement::tests
