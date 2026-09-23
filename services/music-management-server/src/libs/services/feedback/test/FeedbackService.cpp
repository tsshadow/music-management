/*
 * Copyright (C) 2026 Teun Schriks
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

#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "database/objects/RatedTrack.hpp"

#include "Common.hpp"
#include "FeedbackService.hpp"

int main(int argc, char** argv)
{
    using namespace lms;
    core::Service<core::logging::ILogger> logger{ core::logging::createLogger(core::logging::Severity::ERROR) };

    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}

namespace lms::feedback::tests
{
    namespace
    {
        // Records what the service tells a backend, and nothing else.
        class RecordingBackend final : public IFeedbackBackend
        {
        public:
            std::vector<db::RatedTrackId> changedTracks;
            std::vector<RatingRemovedEvent> removed;

        private:
            void onStarred(db::StarredArtistId) override {}
            void onUnstarred(db::StarredArtistId) override {}
            void onStarred(db::StarredReleaseId) override {}
            void onUnstarred(db::StarredReleaseId) override {}
            void onStarred(db::StarredTrackId) override {}
            void onUnstarred(db::StarredTrackId) override {}
            void onRatingChanged(db::RatedArtistId) override {}
            void onRatingChanged(db::RatedReleaseId) override {}
            void onRatingChanged(db::RatedTrackId trackId) override { changedTracks.push_back(trackId); }
            void onRatingRemoved(const RatingRemovedEvent& event) override { removed.push_back(event); }
            void onPlaylistChanged(db::TrackListId) override {}
        };

        class FeedbackServiceTest : public db::tests::DatabaseFixture
        {
        protected:
            // A service whose only backend is a recorder, registered under MusicManagement --
            // the default every user gets.
            std::unique_ptr<IFeedbackService> createService()
            {
                auto backend{ std::make_unique<RecordingBackend>() };
                recorder = backend.get();

                FeedbackService::Backends backends;
                backends.emplace(db::FeedbackBackend::MusicManagement, std::move(backend));
                return std::make_unique<FeedbackService>(session.getDb(), std::move(backends));
            }

            RecordingBackend* recorder{};
        };
    } // namespace

    TEST_F(FeedbackServiceTest, settingARatingNotifiesTheBackend)
    {
        const auto service{ createService() };
        db::tests::ScopedTrack track{ session };
        db::tests::ScopedUser user{ session, "MyUser" };

        service->setRating(user.getId(), track.getId(), 4);
        EXPECT_EQ(recorder->changedTracks.size(), 1);
        EXPECT_TRUE(recorder->removed.empty());

        service->setRating(user.getId(), track.getId(), std::nullopt);
    }

    // Clearing a rating deleted the row and then notified with the deleted row's id; the MuMa
    // backend looked it up, found nothing, and sent nothing, so MuMa kept the old star forever.
    // The payload is captured before the row goes, and reported as a removal.
    TEST_F(FeedbackServiceTest, clearingARatingReportsTheRemovalWithItsPayload)
    {
        const auto service{ createService() };
        db::tests::ScopedTrack track{ session };
        db::tests::ScopedUser user{ session, "MyUser" };

        service->setRating(user.getId(), track.getId(), 3);
        service->setRating(user.getId(), track.getId(), std::nullopt);

        ASSERT_EQ(recorder->removed.size(), 1);
        const RatingRemovedEvent& event{ recorder->removed.front() };
        EXPECT_EQ(event.objectType, "track");
        EXPECT_EQ(event.objectId, track.getId().toString());
        EXPECT_EQ(event.username, "MyUser");
        EXPECT_EQ(event.previousRating, 3);
        EXPECT_EQ(recorder->changedTracks.size(), 1); // the set only, not the clear

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_FALSE(db::RatedTrack::find(session, track.getId(), user.getId()));
        }
    }

    TEST_F(FeedbackServiceTest, clearingARatingThatDoesNotExistReportsNothing)
    {
        const auto service{ createService() };
        db::tests::ScopedTrack track{ session };
        db::tests::ScopedUser user{ session, "MyUser" };

        service->setRating(user.getId(), track.getId(), std::nullopt);

        EXPECT_TRUE(recorder->changedTracks.empty());
        EXPECT_TRUE(recorder->removed.empty());
    }

    // A user whose stored backend has no instance -- ListenBrainz is not registered here, the
    // same way an out-of-range value from /updateUser had none -- used to make the service
    // insert a null into the backend map and call through it: a segfault for the whole server.
    TEST_F(FeedbackServiceTest, aBackendWithNoInstanceIsSkippedNotDereferenced)
    {
        const auto service{ createService() };
        db::tests::ScopedTrack track{ session };
        db::tests::ScopedUser user{ session, "MyUser" };
        {
            auto transaction{ session.createWriteTransaction() };
            user.get().modify()->setFeedbackBackend(db::FeedbackBackend::ListenBrainz);
        }

        EXPECT_NO_THROW(service->setRating(user.getId(), track.getId(), 5));
        EXPECT_NO_THROW(service->setRating(user.getId(), track.getId(), std::nullopt));

        EXPECT_TRUE(recorder->changedTracks.empty());
        EXPECT_TRUE(recorder->removed.empty());
    }
} // namespace lms::feedback::tests
