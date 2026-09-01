/*
 * copyright (c) 2026 emeric poupon
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

#include <gtest/gtest.h>

#include "endpoints/Memories.hpp"

namespace lms::api::subsonic::memories::tests
{
    TEST(Memories, groupsByYearNewestFirst)
    {
        const std::vector<DatedTrack> tracks{
            { db::TrackId{ 1 }, 2018, true },
            { db::TrackId{ 2 }, 2018, false },
            { db::TrackId{ 3 }, 2015, false },
        };

        const std::vector<Group> groups{ groupByYear(tracks, 10) };

        ASSERT_EQ(groups.size(), 2);
        EXPECT_EQ(groups[0].year, 2018);
        EXPECT_TRUE(groups[0].exact);
        EXPECT_EQ(groups[0].trackIds.size(), 2);
        EXPECT_EQ(groups[1].year, 2015);
        EXPECT_FALSE(groups[1].exact);
    }

    TEST(Memories, truncationKeepsExactMatches)
    {
        // Equally loved tracks are separated by the date: an anniversary beats a near miss.
        const std::vector<DatedTrack> tracks{
            { db::TrackId{ 1 }, 2018, false },
            { db::TrackId{ 2 }, 2018, true },
            { db::TrackId{ 3 }, 2018, false },
        };

        const std::vector<Group> groups{ groupByYear(tracks, 1) };

        ASSERT_EQ(groups.size(), 1);
        ASSERT_EQ(groups[0].trackIds.size(), 1);
        EXPECT_EQ(groups[0].trackIds[0], db::TrackId{ 2 });
    }

    TEST(Memories, ordersAYearByWhatTheListenerLovesMost)
    {
        // A five-star track outranks everything; below that the listen count decides.
        const std::vector<DatedTrack> tracks{
            { db::TrackId{ 1 }, 2018, true, false, 90 },
            { db::TrackId{ 2 }, 2018, true, true, 2 },
            { db::TrackId{ 3 }, 2018, true, false, 120 },
        };

        const std::vector<Group> groups{ groupByYear(tracks, 10) };

        ASSERT_EQ(groups.size(), 1);
        ASSERT_EQ(groups[0].trackIds.size(), 3);
        EXPECT_EQ(groups[0].trackIds[0], db::TrackId{ 2 });
        EXPECT_EQ(groups[0].trackIds[1], db::TrackId{ 3 });
        EXPECT_EQ(groups[0].trackIds[2], db::TrackId{ 1 });
    }

    TEST(Memories, ranksAReleaseOnALabelAboveARipFromAPlatform)
    {
        // Nothing rated, nothing played: the release itself decides. A label release is the most
        // deliberate thing in the year, an import placeholder the least.
        EXPECT_GT(sourceRank({ "Roughstate" }), sourceRank({}));
        EXPECT_GT(sourceRank({}), sourceRank({ "__Free&None" }));
        EXPECT_GT(sourceRank({ "__Free&None" }), sourceRank({ "Soundcloud" }));
        EXPECT_GT(sourceRank({ "Soundcloud" }), sourceRank({ "Youtube" }));
        EXPECT_GT(sourceRank({ "Youtube" }), sourceRank({ "Telegram" }));
        EXPECT_GT(sourceRank({ "Telegram" }), sourceRank({ "__TODO" }));
    }

    TEST(Memories, readsPlatformNamesWhateverTheTagsCapitalisationOrPadding)
    {
        // The same placeholder exists with two and with three underscores, and the publisher tag's
        // capitalisation is whatever the downloader wrote that day.
        EXPECT_EQ(sourceRank({ "SOUNDCLOUD" }), sourceRank({ "Soundcloud" }));
        EXPECT_EQ(sourceRank({ "___Free&None" }), sourceRank({ "__Free&None" }));
        EXPECT_EQ(sourceRank({ "youtube" }), sourceRank({ "Youtube" }));
    }

    TEST(Memories, aReleaseWithSeveralLabelsTakesItsBestOne)
    {
        EXPECT_EQ(sourceRank({ "Soundcloud", "Roughstate" }), sourceRank({ "Roughstate" }));
    }

    TEST(Memories, ordersAYearBySourceWhenNothingIsRatedOrPlayed)
    {
        const std::vector<DatedTrack> tracks{
            { db::TrackId{ 1 }, 2018, true, false, 0, sourceRank({ "Soundcloud" }) },
            { db::TrackId{ 2 }, 2018, true, false, 0, sourceRank({ "__TODO" }) },
            { db::TrackId{ 3 }, 2018, true, false, 0, sourceRank({ "Roughstate" }) },
        };

        const std::vector<Group> groups{ groupByYear(tracks, 10) };

        ASSERT_EQ(groups.size(), 1);
        EXPECT_EQ(groups[0].trackIds[0], db::TrackId{ 3 });
        EXPECT_EQ(groups[0].trackIds[1], db::TrackId{ 1 });
        EXPECT_EQ(groups[0].trackIds[2], db::TrackId{ 2 });
    }

    TEST(Memories, listensStillOutrankTheRelease)
    {
        // The source is a fallback for a year nobody has touched, not a reason to bury a track the
        // listener actually plays.
        const std::vector<DatedTrack> tracks{
            { db::TrackId{ 1 }, 2018, true, false, 0, sourceRank({ "Roughstate" }) },
            { db::TrackId{ 2 }, 2018, true, false, 7, sourceRank({ "Soundcloud" }) },
        };

        const std::vector<Group> groups{ groupByYear(tracks, 10) };

        ASSERT_EQ(groups.size(), 1);
        EXPECT_EQ(groups[0].trackIds[0], db::TrackId{ 2 });
    }

    TEST(Memories, reportsTheYearsFullSizeNotThePageSize)
    {
        // The tile shows a count and the page shows a page; conflating the two makes a big year
        // claim to be exactly as large as the limit that truncated it.
        const std::vector<DatedTrack> tracks{
            { db::TrackId{ 1 }, 2018, true, false, 3 },
            { db::TrackId{ 2 }, 2018, true, false, 2 },
            { db::TrackId{ 3 }, 2018, true, false, 1 },
        };

        const std::vector<Group> groups{ groupByYear(tracks, 2) };

        ASSERT_EQ(groups.size(), 1);
        EXPECT_EQ(groups[0].total, 3);
        EXPECT_EQ(groups[0].trackIds.size(), 2);
    }

    TEST(Memories, keepsTheWholeYearBesideThePage)
    {
        // A tile lists the page but needs covers from anywhere in the year, because the tracks that
        // rank highest are often exactly the ones without artwork.
        const std::vector<DatedTrack> tracks{
            { db::TrackId{ 1 }, 2018, true, false, 3 },
            { db::TrackId{ 2 }, 2018, true, false, 2 },
            { db::TrackId{ 3 }, 2018, true, false, 1 },
        };

        const std::vector<Group> groups{ groupByYear(tracks, 1) };

        ASSERT_EQ(groups.size(), 1);
        ASSERT_EQ(groups[0].trackIds.size(), 1);
        ASSERT_EQ(groups[0].rankedIds.size(), 3);
        EXPECT_EQ(groups[0].rankedIds[0], db::TrackId{ 1 });
        EXPECT_EQ(groups[0].rankedIds[2], db::TrackId{ 3 });
    }

    TEST(Memories, emptyInputYieldsNoGroups)
    {
        EXPECT_TRUE(groupByYear({}, 10).empty());
    }

    TEST(Memories, outOfRangeParametersAreClampedNotRejected)
    {
        EXPECT_EQ(clampWindowDays(999), maxWindowDays);
        EXPECT_EQ(clampWindowDays(0), std::size_t{ 0 });
        EXPECT_EQ(clampMaxPerYear(0), std::size_t{ 1 });
        EXPECT_EQ(clampMaxPerYear(9999), maxMaxPerYear);
    }

    TEST(Memories, parsesAnIsoDateAndRejectsGarbage)
    {
        const auto parsed{ parseIsoDate("2020-08-02") };
        ASSERT_TRUE(parsed.has_value());
        EXPECT_EQ(parsed->year(), 2020);
        EXPECT_EQ(parsed->month(), 8);
        EXPECT_EQ(parsed->day(), 2);

        EXPECT_FALSE(parseIsoDate("2020-13-45").has_value());
        EXPECT_FALSE(parseIsoDate("not a date").has_value());
        EXPECT_FALSE(parseIsoDate("").has_value());
    }
} // namespace lms::api::subsonic::memories::tests
