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

// One row per song outside the song page (bug report 096). muma groups the versions of one
// song into a work and names its canonical; these tests pin the lookups the Subsonic lists build
// on, each in the exact FindParameters shape its endpoint sends: search3's keyword search,
// getRandomSongs' shuffle, getSongsByGenre's genre list, getStarred2's collapse of a favourite
// version onto its canonical, and the version walk behind clearing a song's rating. Albums and
// playlists are deliberately not collapsed -- they are a context the user or the release chose --
// so nothing here covers them.

#include <algorithm>
#include <set>
#include <vector>

#include "database/objects/Cluster.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"

#include "Common.hpp"

namespace lms::db::tests
{
    namespace
    {
        constexpr int work{ 394638 };

        // KOPPEN ROLLEN, as on Teun's radar on 2026-09-26: the official release (canonical),
        // a SoundCloud rip of the same song, and an unrelated song muma has not grouped.
        class SongVersionsTest : public DatabaseFixture
        {
        protected:
            void SetUp() override
            {
                auto transaction{ session.createWriteTransaction() };
                official.get().modify()->setName("Koppen Rollen");
                official.get().modify()->setWorkId(work);
                official.get().modify()->setIsCanonical(true);

                rip.get().modify()->setName("Koppen Rollen");
                rip.get().modify()->setWorkId(work);
                rip.get().modify()->setIsCanonical(false);

                ungrouped.get().modify()->setName("Koppen Rollen (Bootleg)");
            }

            std::vector<TrackId> ids(const Track::FindParameters& params)
            {
                auto transaction{ session.createReadTransaction() };
                return Track::findIds(session, params).results;
            }

            static bool contains(const std::vector<TrackId>& found, TrackId id)
            {
                return std::find(found.cbegin(), found.cend(), id) != found.cend();
            }

            ScopedTrack official{ session };
            ScopedTrack rip{ session };
            ScopedTrack ungrouped{ session };
        };
    } // namespace

    TEST_F(SongVersionsTest, withoutTheFilterEveryVersionIsListed)
    {
        // The song page and the albums: they keep every file.
        EXPECT_EQ(ids(Track::FindParameters{}).size(), 3);
    }

    TEST_F(SongVersionsTest, aWorkListsEveryVersion)
    {
        // What clearing a song's rating walks: unstarring the canonical from a list clears the
        // rating on every version, or the row would fall back to the rip's star.
        Track::FindParameters params;
        params.workId = work;
        const std::vector<TrackId> found{ ids(params) };
        ASSERT_EQ(found.size(), 2);
        EXPECT_TRUE(contains(found, official.getId()));
        EXPECT_TRUE(contains(found, rip.getId()));
    }

    TEST_F(SongVersionsTest, search3FindsTheSongOnce)
    {
        Track::FindParameters params;
        params.setKeywords({ "Koppen" });
        params.setSortMethod(TrackSortMethod::Id);
        params.canonicalOnly = true;

        const std::vector<TrackId> found{ ids(params) };
        ASSERT_EQ(found.size(), 2);
        EXPECT_TRUE(contains(found, official.getId()));
        // Not grouped yet, so it has no canonical to lose to: hiding it would hide music.
        EXPECT_TRUE(contains(found, ungrouped.getId()));
        EXPECT_FALSE(contains(found, rip.getId()));
    }

    TEST_F(SongVersionsTest, getRandomSongsDrawsSongsNotFiles)
    {
        Track::FindParameters params;
        params.setSortMethod(TrackSortMethod::Random);
        params.setRange(Range{ 0, 50 });
        params.canonicalOnly = true;

        const std::vector<TrackId> found{ ids(params) };
        EXPECT_EQ(found.size(), 2);
        EXPECT_FALSE(contains(found, rip.getId()));
    }

    TEST_F(SongVersionsTest, getSongsByGenreListsTheSongOnce)
    {
        ScopedUser user{ session, "user" };
        ScopedClusterType genreType{ session, "GENRE" };
        ScopedCluster uptempo{ session, genreType.lockAndGet(), "Uptempo" };
        {
            auto transaction{ session.createWriteTransaction() };
            uptempo.get().modify()->addTrack(official.get());
            uptempo.get().modify()->addTrack(rip.get());
        }

        Track::FindParameters params;
        params.filters.setClusters(std::vector<ClusterId>{ uptempo.getId() });
        params.setRange(Range{ 0, 10 });
        params.setMinRating(0);
        params.setMaxRating(5);
        params.ratingUser = user.getId();
        params.includeUnrated = true;
        params.canonicalOnly = true;

        const std::vector<TrackId> found{ ids(params) };
        ASSERT_EQ(found.size(), 1);
        EXPECT_EQ(found.front(), official.getId());
    }

    TEST_F(SongVersionsTest, getStarred2ShowsAFavouriteVersionAsItsCanonical)
    {
        auto transaction{ session.createReadTransaction() };
        const Track::pointer shown{ Track::findCanonicalVersion(session, rip.get()) };
        ASSERT_TRUE(shown);
        EXPECT_EQ(shown->getId(), official.getId());
    }

    TEST_F(SongVersionsTest, theCanonicalAndAnUngroupedTrackStandForThemselves)
    {
        auto transaction{ session.createReadTransaction() };
        EXPECT_EQ(Track::findCanonicalVersion(session, official.get())->getId(), official.getId());
        EXPECT_EQ(Track::findCanonicalVersion(session, ungrouped.get())->getId(), ungrouped.getId());
        EXPECT_FALSE(Track::findCanonicalVersion(session, Track::pointer{}));
    }

    TEST_F(SongVersionsTest, aVersionWhoseCanonicalThisServerLacksIsShownItself)
    {
        // muma named a canonical this server does not hold (a path that did not match): the
        // list shows the version rather than nothing.
        {
            auto transaction{ session.createWriteTransaction() };
            official.get().modify()->setIsCanonical(false);
        }
        auto transaction{ session.createReadTransaction() };
        EXPECT_EQ(Track::findCanonicalVersion(session, rip.get())->getId(), rip.getId());
    }

    TEST_F(SongVersionsTest, theSongRatingIsTheHighestOnAnyVersion)
    {
        ScopedUser user{ session, "user" };
        ScopedUser other{ session, "other" };
        {
            auto transaction{ session.createWriteTransaction() };
            session.create<RatedTrack>(official.get(), user.get()).modify()->setRating(3);
            session.create<RatedTrack>(rip.get(), user.get()).modify()->setRating(5);
            // Somebody else's rating is theirs alone.
            session.create<RatedTrack>(official.get(), other.get()).modify()->setRating(1);
        }

        auto transaction{ session.createReadTransaction() };
        const RatedTrack::pointer highest{ RatedTrack::findHighestInWork(session, work, user.getId()) };
        ASSERT_TRUE(highest);
        EXPECT_EQ(highest->getRating(), 5);

        const RatedTrack::pointer others{ RatedTrack::findHighestInWork(session, work, other.getId()) };
        ASSERT_TRUE(others);
        EXPECT_EQ(others->getRating(), 1);
    }

    TEST_F(SongVersionsTest, anUnratedSongHasNoSongRating)
    {
        ScopedUser user{ session, "user" };
        auto transaction{ session.createReadTransaction() };
        EXPECT_FALSE(RatedTrack::findHighestInWork(session, work, user.getId()));
    }
} // namespace lms::db::tests
