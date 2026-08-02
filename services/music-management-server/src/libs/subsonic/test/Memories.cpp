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
}
