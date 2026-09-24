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

#include <algorithm>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "SubsonicResponse.hpp"
#include "endpoints/SpotifyPaging.hpp"

namespace lms::api::subsonic::tests
{
    using namespace spotifyPaging;

    namespace
    {
        // A library row: its position in the underlying list and the song (work) it belongs to.
        struct Row
        {
            std::size_t position;
            std::string work;
        };

        // Serves [offset, offset + size) of \p rows, like one find_advanced call with a range.
        auto fetchFrom(const std::vector<Row>& rows)
        {
            return [&rows](std::size_t offset, std::size_t size, const auto& visit) {
                for (std::size_t i{ offset }; i < rows.size() && i < offset + size; ++i)
                    visit(rows[i]);
            };
        }

        std::string keyOf(const Row& row)
        {
            return row.work;
        }

        bool neverReplace(const Row&, const Row&)
        {
            return false;
        }

        std::vector<std::string> worksOf(const std::vector<Row>& rows)
        {
            std::vector<std::string> works;
            for (const Row& row : rows)
                works.push_back(row.work);
            return works;
        }

        // Pages through \p rows the way a client does -- each request starting at the previous
        // nextOffset -- and returns every work shown, in order.
        std::vector<std::string> pageThrough(const std::vector<Row>& rows, std::size_t pageSize, std::size_t scanBatchSize)
        {
            std::vector<std::string> shown;
            std::size_t offset{};
            for (int guard{}; guard < 100; ++guard)
            {
                std::vector<Row> page;
                const DedupedPageResult result{ collectDedupedPage<Row>(offset, pageSize, scanBatchSize, 5000, fetchFrom(rows), keyOf, neverReplace, page) };
                for (const std::string& work : worksOf(page))
                    shown.push_back(work);
                if (!result.moreResults)
                    break;
                offset = result.nextOffset;
            }
            return shown;
        }
    } // namespace

    TEST(SpotifyPaging, rangeDefaultsWhenNothingIsSent)
    {
        const db::Range range{ parseRange(std::nullopt, std::nullopt) };
        EXPECT_EQ(range.offset, 0);
        EXPECT_EQ(range.size, defaultPageSize);
    }

    // count=-1 used to wrap to SIZE_MAX and walk the whole library in one request.
    TEST(SpotifyPaging, negativeOffsetOrCountIsABadParameter)
    {
        EXPECT_THROW(parseRange(-1, 50), BadParameterGenericError);
        EXPECT_THROW(parseRange(0, -1), BadParameterGenericError);
        EXPECT_THROW(parseRange(-5, -5), BadParameterGenericError);
    }

    TEST(SpotifyPaging, countIsClampedToTheMaximumPage)
    {
        EXPECT_EQ(parseRange(0, 500).size, 500); // the largest page a client legitimately asks for
        EXPECT_EQ(parseRange(0, static_cast<int>(maxPageSize)).size, maxPageSize);
        EXPECT_EQ(parseRange(0, static_cast<int>(maxPageSize) + 1).size, maxPageSize);
        EXPECT_EQ(parseRange(0, 2147483647).size, maxPageSize);
        EXPECT_EQ(parseRange(123, 0).size, 0);
        EXPECT_EQ(parseRange(123, 0).offset, 123);
    }

    TEST(SpotifyPaging, uniqueRowsFillThePageAndAdvanceByWhatWasShown)
    {
        std::vector<Row> rows;
        for (std::size_t i{}; i < 10; ++i)
            rows.push_back(Row{ i, "w" + std::to_string(i) });

        std::vector<Row> page;
        const DedupedPageResult result{ collectDedupedPage<Row>(0, 3, 5, 5000, fetchFrom(rows), keyOf, neverReplace, page) };
        EXPECT_EQ(worksOf(page), (std::vector<std::string>{ "w0", "w1", "w2" }));
        EXPECT_EQ(result.nextOffset, 3);
        EXPECT_TRUE(result.moreResults);
    }

    // The defect: the page filled part-way through a scan batch, yet nextOffset jumped past the
    // whole batch, so the rows after the last one shown were never shown on any page.
    TEST(SpotifyPaging, dedupeAcrossAPageBoundaryLosesNoRows)
    {
        // w1 appears twice before the page boundary, so the first page consumes four rows to
        // show three works; w4..w9 follow in the same scan batch.
        const std::vector<Row> rows{
            { 0, "w0" }, { 1, "w1" }, { 2, "w1" }, { 3, "w2" }, { 4, "w3" }, { 5, "w4" }, { 6, "w5" }, { 7, "w6" }, { 8, "w7" }, { 9, "w8" }, { 10, "w9" }
        };

        std::vector<Row> page;
        const DedupedPageResult first{ collectDedupedPage<Row>(0, 3, 100, 5000, fetchFrom(rows), keyOf, neverReplace, page) };
        EXPECT_EQ(worksOf(page), (std::vector<std::string>{ "w0", "w1", "w2" }));
        EXPECT_EQ(first.nextOffset, 4); // the old code answered 11: the whole batch
        EXPECT_TRUE(first.moreResults); // the batch was short, but the page cut it off

        EXPECT_EQ(pageThrough(rows, 3, 100), (std::vector<std::string>{ "w0", "w1", "w2", "w3", "w4", "w5", "w6", "w7", "w8", "w9" }));
    }

    TEST(SpotifyPaging, everyRowIsShownWhateverTheBatchSize)
    {
        std::vector<Row> rows;
        std::vector<std::string> expected;
        for (std::size_t i{}; i < 40; ++i)
        {
            // Every third work has a second version right after it.
            rows.push_back(Row{ rows.size(), "w" + std::to_string(i) });
            expected.push_back("w" + std::to_string(i));
            if (i % 3 == 0)
                rows.push_back(Row{ rows.size(), "w" + std::to_string(i) });
        }

        // Versions are merged within a page only, so a pair straddling a page boundary shows up
        // on both pages; what must never happen is a work that shows up on none.
        for (const std::size_t batchSize : std::vector<std::size_t>{ 1, 2, 3, 7, 100 })
        {
            for (const std::size_t pageSize : std::vector<std::size_t>{ 1, 2, 5, 50 })
            {
                std::vector<std::string> firstAppearances;
                for (const std::string& work : pageThrough(rows, pageSize, batchSize))
                {
                    if (std::find(firstAppearances.begin(), firstAppearances.end(), work) == firstAppearances.end())
                        firstAppearances.push_back(work);
                }
                EXPECT_EQ(firstAppearances, expected) << "batch " << batchSize << ", page " << pageSize;
            }
        }
    }

    TEST(SpotifyPaging, theLastPageSaysThereIsNoMore)
    {
        const std::vector<Row> rows{ { 0, "w0" }, { 1, "w1" } };

        std::vector<Row> page;
        const DedupedPageResult result{ collectDedupedPage<Row>(0, 5, 100, 5000, fetchFrom(rows), keyOf, neverReplace, page) };
        EXPECT_EQ(page.size(), 2);
        EXPECT_EQ(result.nextOffset, 2);
        EXPECT_FALSE(result.moreResults);
    }

    TEST(SpotifyPaging, aLaterVersionCanReplaceTheKeptOne)
    {
        const std::vector<Row> rows{ { 0, "w0" }, { 1, "w0" }, { 2, "w1" } };

        std::vector<Row> page;
        collectDedupedPage<Row>(0, 5, 100, 5000, fetchFrom(rows), keyOf, [](const Row&, const Row& candidate) { return candidate.position == 1; }, page);
        ASSERT_EQ(page.size(), 2);
        EXPECT_EQ(page[0].position, 1);
        EXPECT_EQ(page[1].position, 2);
    }

    // The scan cap still bounds a request whose rows are all versions of one song.
    TEST(SpotifyPaging, scanningStopsAtTheCap)
    {
        std::vector<Row> rows;
        for (std::size_t i{}; i < 1000; ++i)
            rows.push_back(Row{ i, "same" });

        std::vector<Row> page;
        const DedupedPageResult result{ collectDedupedPage<Row>(0, 5, 100, 300, fetchFrom(rows), keyOf, neverReplace, page) };
        EXPECT_EQ(page.size(), 1);
        EXPECT_EQ(result.nextOffset, 300);
        EXPECT_TRUE(result.moreResults);
    }
} // namespace lms::api::subsonic::tests
