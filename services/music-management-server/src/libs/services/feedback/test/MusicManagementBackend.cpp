/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <memory>

#include <gtest/gtest.h>

#include <Wt/Http/Message.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>

#include "database/objects/Artist.hpp"
#include "database/objects/RatedArtist.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"

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

        // The rating relay to MuMa's /api/rating/lms-event, with the network replaced by a recorder.
        class MusicManagementFeedback : public db::tests::DatabaseFixture
        {
        protected:
            std::unique_ptr<IFeedbackBackend> createBackend()
            {
                return std::make_unique<MusicManagementBackend>(session.getDb(), std::make_unique<FakeHttpClient>(sent), "system-key");
            }

            std::shared_ptr<SentRequests> sent{ std::make_shared<SentRequests>() };
            db::tests::ScopedTrack track{ session };
            db::tests::ScopedArtist artist{ session, "Angerfist" };
            db::tests::ScopedUser user{ session, "user" };
        };
    } // namespace

    // MuMa finds the track by its path (the LMS id means nothing there), so the path is the load-
    // bearing field of a track rating.
    TEST_F(MusicManagementFeedback, aTrackRatingCarriesUserRatingAndPath)
    {
        const auto backend{ createBackend() };
        db::RatedTrackId ratedTrackId;
        {
            auto transaction{ session.createWriteTransaction() };
            track.get().modify()->setAbsoluteFilePath("/music/Angerfist/Raise Your Fist.mp3");
            db::RatedTrack::pointer rated{ session.create<db::RatedTrack>(track.get(), user.getId()) };
            rated.modify()->setRating(4);
            ratedTrackId = rated->getId();
        }

        backend->onRatingChanged(ratedTrackId);

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ parseBody(sent->posts.front()) };
        EXPECT_EQ(static_cast<std::string>(body.get("event")), "rating_changed");
        EXPECT_EQ(static_cast<std::string>(body.get("object_type")), "track");
        EXPECT_EQ(static_cast<std::string>(body.get("object_id")), track.getId().toString());
        EXPECT_EQ(static_cast<std::string>(body.get("username")), "user");
        EXPECT_EQ(static_cast<int>(body.get("rating")), 4);
        EXPECT_EQ(static_cast<std::string>(body.get("path")), "/music/Angerfist/Raise Your Fist.mp3");
        const std::string* key{ sent->posts.front().message.getHeader("X-API-Key") };
        ASSERT_NE(key, nullptr);
        EXPECT_EQ(*key, "system-key");

        {
            auto transaction{ session.createWriteTransaction() };
            db::RatedTrack::find(session, ratedTrackId).remove();
        }
    }

    TEST_F(MusicManagementFeedback, anArtistRatingIsNamedAndHasNoPath)
    {
        const auto backend{ createBackend() };
        db::RatedArtistId ratedArtistId;
        {
            auto transaction{ session.createWriteTransaction() };
            db::RatedArtist::pointer rated{ session.create<db::RatedArtist>(artist.get(), user.getId()) };
            rated.modify()->setRating(5);
            ratedArtistId = rated->getId();
        }

        backend->onRatingChanged(ratedArtistId);

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ parseBody(sent->posts.front()) };
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
        const auto backend{ createBackend() };

        backend->onRatingRemoved(RatingRemovedEvent{ .objectType = "track", .objectId = "12", .username = "user", .path = "/music/a.mp3", .previousRating = 3 });

        ASSERT_EQ(sent->posts.size(), 1);
        const Wt::Json::Object body{ parseBody(sent->posts.front()) };
        EXPECT_EQ(static_cast<std::string>(body.get("event")), "rating_removed");
        EXPECT_EQ(static_cast<int>(body.get("rating")), 0);
        EXPECT_EQ(static_cast<std::string>(body.get("path")), "/music/a.mp3");
    }

    TEST_F(MusicManagementFeedback, aRatingThatNoLongerExistsSendsNothing)
    {
        const auto backend{ createBackend() };

        backend->onRatingChanged(db::RatedTrackId{ 987654 });
        backend->onRatingChanged(db::RatedArtistId{ 987654 });

        EXPECT_TRUE(sent->posts.empty());
    }

    // Stars are not mirrored to MuMa at all; only ratings are.
    TEST_F(MusicManagementFeedback, starsAreNotRelayed)
    {
        const auto backend{ createBackend() };

        backend->onStarred(db::StarredTrackId{ 1 });
        backend->onUnstarred(db::StarredTrackId{ 1 });
        backend->onStarred(db::StarredArtistId{ 1 });
        backend->onStarred(db::StarredReleaseId{ 1 });

        EXPECT_TRUE(sent->posts.empty());
    }

    // Pins how the send queue treats a rating event, as it is today: a plain request, so only a 200
    // counts as delivered. Any other answer, or a connection that never succeeds within the queue's
    // retries, ends in onFailureFunc, which logs and drops the event -- MuMa's mirror keeps the old
    // rating until the next change. Neither callback may throw back into the queue.
    TEST_F(MusicManagementFeedback, aRatingEventIsDeliveredOrLoggedAndDropped)
    {
        const auto backend{ createBackend() };
        backend->onRatingRemoved(RatingRemovedEvent{ .objectType = "track", .objectId = "12", .username = "user", .path = "/music/a.mp3", .previousRating = 3 });

        ASSERT_EQ(sent->posts.size(), 1);
        const core::http::ClientPOSTRequestParameters& request{ sent->posts.front() };
        EXPECT_FALSE(request.treatAnyStatusAsSuccess);
        ASSERT_TRUE(request.onSuccessFunc);
        ASSERT_TRUE(request.onFailureFunc);

        Wt::Http::Message delivered;
        delivered.setStatus(200);
        EXPECT_NO_THROW(request.onSuccessFunc(delivered));
        EXPECT_NO_THROW(request.onFailureFunc());
    }
} // namespace lms::feedback::musicManagement::tests
