/*
 * Copyright (C) 2026 Emeric Poupon
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

// A radio channel is a stored filter, and getSongsByFilter turns it into exactly
// the FindParameters combination these tests cover: a label, narrowed by duration
// and rating. The label lives on the release rather than the track, which is the
// part worth pinning down -- a track without a release must not slip through a
// label channel.

#include <algorithm>

#include "database/objects/RatedTrack.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"

#include "Common.hpp"

namespace lms::db::tests
{
    namespace
    {
        using ScopedLabel = ScopedEntity<db::Label>;
    }

    TEST_F(DatabaseFixture, RadioFilters_label)
    {
        ScopedLabel label{ session, "Q-dance Records" };
        ScopedLabel otherLabel{ session, "Dirty Workz" };
        ScopedRelease release{ session, "Release" };
        ScopedRelease otherRelease{ session, "OtherRelease" };
        ScopedTrack onLabel{ session };
        ScopedTrack onOtherLabel{ session };
        ScopedTrack withoutRelease{ session };

        {
            auto transaction{ session.createWriteTransaction() };

            release.get().modify()->addLabel(label.get());
            otherRelease.get().modify()->addLabel(otherLabel.get());
            onLabel.get().modify()->setRelease(release.get());
            onOtherLabel.get().modify()->setRelease(otherRelease.get());
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            params.filters.setLabel(label.getId());

            const auto results{ Track::findIds(session, params).results };

            ASSERT_EQ(results.size(), 1);
            EXPECT_EQ(results.front(), onLabel.getId());
        }
    }

    TEST_F(DatabaseFixture, RadioFilters_labelWithDurationAndRating)
    {
        ScopedUser user{ session, "radio" };
        ScopedLabel label{ session, "Q-dance Records" };
        ScopedRelease release{ session, "Release" };
        ScopedTrack shortLiked{ session };  // 3 min, rated 4
        ScopedTrack longLiked{ session };   // 9 min, rated 4
        ScopedTrack shortDisliked{ session }; // 3 min, rated 2
        ScopedTrack shortUnrated{ session }; // 3 min, no rating

        {
            auto transaction{ session.createWriteTransaction() };

            release.get().modify()->addLabel(label.get());
            for (ScopedTrack* track : { &shortLiked, &longLiked, &shortDisliked, &shortUnrated })
                track->get().modify()->setRelease(release.get());

            shortLiked.get().modify()->setDuration(std::chrono::minutes{ 3 });
            longLiked.get().modify()->setDuration(std::chrono::minutes{ 9 });
            shortDisliked.get().modify()->setDuration(std::chrono::minutes{ 3 });
            shortUnrated.get().modify()->setDuration(std::chrono::minutes{ 3 });

            session.create<RatedTrack>(shortLiked.get(), user.get()).modify()->setRating(4);
            session.create<RatedTrack>(longLiked.get(), user.get()).modify()->setRating(4);
            session.create<RatedTrack>(shortDisliked.get(), user.get()).modify()->setRating(2);
        }

        {
            auto transaction{ session.createReadTransaction() };

            // What "Q-dance Records, four stars and up, under five minutes" builds.
            Track::FindParameters params;
            params.filters.setLabel(label.getId());
            params.minRating = 4;
            params.ratingUser = user.getId();
            params.includeUnrated = false;
            params.maxDuration = std::chrono::seconds{ 300 };

            const auto results{ Track::findIds(session, params).results };

            ASSERT_EQ(results.size(), 1);
            EXPECT_EQ(results.front(), shortLiked.getId());
        }

        {
            auto transaction{ session.createReadTransaction() };

            // includeUnrated is what decides whether a channel with a rating floor
            // still plays tracks nobody has rated yet.
            Track::FindParameters params;
            params.filters.setLabel(label.getId());
            params.minRating = 4;
            params.ratingUser = user.getId();
            params.includeUnrated = true;
            params.maxDuration = std::chrono::seconds{ 300 };

            const auto results{ Track::findIds(session, params).results };

            ASSERT_EQ(results.size(), 2);
            EXPECT_NE(std::find(results.begin(), results.end(), shortLiked.getId()), results.end());
            EXPECT_NE(std::find(results.begin(), results.end(), shortUnrated.getId()), results.end());
        }
    }

    TEST_F(DatabaseFixture, RadioFilters_randomSeedIsStable)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };
        ScopedTrack track3{ session };

        const auto findWithSeed{ [this](int seed) {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            params.setSortMethod(TrackSortMethod::Random);
            params.randomSeed = seed;

            return Track::findIds(session, params).results;
        } };

        const auto first{ findWithSeed(42) };
        ASSERT_EQ(first.size(), 3);
        EXPECT_EQ(findWithSeed(42), first);
    }
} // namespace lms::db::tests
