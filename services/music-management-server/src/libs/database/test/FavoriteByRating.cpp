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

// There is no separate "favorite" flag any more: something is a favorite exactly
// when it carries the highest rating. These tests cover the queries the feedback
// service uses to answer that question for artists, releases and tracks.

#include "database/objects/RatedArtist.hpp"
#include "database/objects/RatedRelease.hpp"
#include "database/objects/RatedTrack.hpp"

#include "Common.hpp"

namespace lms::db::tests
{
    namespace
    {
        constexpr Rating favoriteRating{ 5 };
    }

    TEST_F(DatabaseFixture, FavoriteByRating_releases)
    {
        ScopedUser user{ session, "testuser" };
        ScopedUser otherUser{ session, "otheruser" };
        ScopedRelease favorite{ session, "Favorite" };
        ScopedRelease liked{ session, "Liked" };
        ScopedRelease unrated{ session, "Unrated" };
        ScopedRelease otherUsersFavorite{ session, "OtherUsersFavorite" };

        {
            auto transaction{ session.createWriteTransaction() };

            session.create<RatedRelease>(favorite.get(), user.get()).modify()->setRating(5);
            session.create<RatedRelease>(liked.get(), user.get()).modify()->setRating(4);
            session.create<RatedRelease>(otherUsersFavorite.get(), otherUser.get()).modify()->setRating(5);
        }

        {
            auto transaction{ session.createReadTransaction() };

            Release::FindParameters params;
            params.setRatingUser(user.getId(), favoriteRating);

            const auto results{ Release::findIds(session, params) };
            ASSERT_EQ(results.results.size(), 1);
            EXPECT_EQ(results.results[0], favorite.getId());
        }
    }

    TEST_F(DatabaseFixture, FavoriteByRating_releasesSortedByMostRecentlyRated)
    {
        ScopedUser user{ session, "testuser" };
        ScopedRelease older{ session, "Older" };
        ScopedRelease newer{ session, "Newer" };

        {
            auto transaction{ session.createWriteTransaction() };

            auto olderRating{ session.create<RatedRelease>(older.get(), user.get()) };
            olderRating.modify()->setRating(5);
            olderRating.modify()->setLastUpdated(Wt::WDateTime{ Wt::WDate{ 2026, 1, 1 } });

            auto newerRating{ session.create<RatedRelease>(newer.get(), user.get()) };
            newerRating.modify()->setRating(5);
            newerRating.modify()->setLastUpdated(Wt::WDateTime{ Wt::WDate{ 2026, 6, 1 } });
        }

        {
            auto transaction{ session.createReadTransaction() };

            Release::FindParameters params;
            params.setRatingUser(user.getId(), favoriteRating);
            params.setSortMethod(ReleaseSortMethod::RatedDateDesc);

            const auto results{ Release::findIds(session, params) };
            ASSERT_EQ(results.results.size(), 2);
            EXPECT_EQ(results.results[0], newer.getId());
            EXPECT_EQ(results.results[1], older.getId());
        }
    }

    TEST_F(DatabaseFixture, FavoriteByRating_artists)
    {
        ScopedUser user{ session, "testuser" };
        ScopedArtist favorite{ session, "Favorite" };
        ScopedArtist liked{ session, "Liked" };
        ScopedArtist unrated{ session, "Unrated" };

        {
            auto transaction{ session.createWriteTransaction() };

            session.create<RatedArtist>(favorite.get(), user.get()).modify()->setRating(5);
            session.create<RatedArtist>(liked.get(), user.get()).modify()->setRating(4);
        }

        {
            auto transaction{ session.createReadTransaction() };

            Artist::FindParameters params;
            params.setRatingUser(user.getId(), favoriteRating);

            const auto results{ Artist::findIds(session, params) };
            ASSERT_EQ(results.results.size(), 1);
            EXPECT_EQ(results.results[0], favorite.getId());
        }
    }

    TEST_F(DatabaseFixture, FavoriteByRating_tracks)
    {
        ScopedUser user{ session, "testuser" };
        ScopedTrack favorite{ session };
        ScopedTrack liked{ session };
        ScopedTrack unrated{ session };

        {
            auto transaction{ session.createWriteTransaction() };

            session.create<RatedTrack>(favorite.get(), user.get()).modify()->setRating(5);
            session.create<RatedTrack>(liked.get(), user.get()).modify()->setRating(4);
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            params.ratingUser = user.getId();
            params.setMinRating(favoriteRating);

            const auto results{ Track::findIds(session, params) };
            ASSERT_EQ(results.results.size(), 1);
            EXPECT_EQ(results.results[0], favorite.getId());
        }
    }

    TEST_F(DatabaseFixture, FavoriteByRating_tracksSortedByMostRecentlyRated)
    {
        ScopedUser user{ session, "testuser" };
        ScopedTrack older{ session };
        ScopedTrack newer{ session };

        {
            auto transaction{ session.createWriteTransaction() };

            auto olderRating{ session.create<RatedTrack>(older.get(), user.get()) };
            olderRating.modify()->setRating(5);
            olderRating.modify()->setLastUpdated(Wt::WDateTime{ Wt::WDate{ 2026, 1, 1 } });

            auto newerRating{ session.create<RatedTrack>(newer.get(), user.get()) };
            newerRating.modify()->setRating(5);
            newerRating.modify()->setLastUpdated(Wt::WDateTime{ Wt::WDate{ 2026, 6, 1 } });
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            params.ratingUser = user.getId();
            params.setMinRating(favoriteRating);
            params.setSortMethod(TrackSortMethod::RatedDateDesc);

            const auto results{ Track::findIds(session, params) };
            ASSERT_EQ(results.results.size(), 2);
            EXPECT_EQ(results.results[0], newer.getId());
            EXPECT_EQ(results.results[1], older.getId());
        }
    }
} // namespace lms::db::tests
