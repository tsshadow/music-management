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

#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include "database/Types.hpp"

#include "SubsonicResponse.hpp"

// Paging for the getSpotify* endpoints (tracks, curated playlists, history). Kept apart from
// Spotify.cpp so the rules can be tested without a database.
namespace lms::api::subsonic::spotifyPaging
{
    /// Page size when the caller does not send count.
    inline constexpr std::size_t defaultPageSize{ 50 };

    /// Largest page any caller gets. The biggest legitimate request is the web player's
    /// 500-track page setting (TRACK_PAGE_SIZES in the frontend's store.js) and Android Auto's
    /// 500-item browse page; anything larger is clamped, so count=-1 or count=10000000 can no
    /// longer walk the whole library in one request.
    inline constexpr std::size_t maxPageSize{ 1000 };

    /// Turns the raw offset/count parameters into a range: a negative value is a bad
    /// parameter (it used to wrap to a huge size_t), and count is clamped to maxPageSize.
    inline db::Range parseRange(std::optional<int> offset, std::optional<int> count)
    {
        if (offset && *offset < 0)
            throw BadParameterGenericError{ "offset", "must not be negative" };
        if (count && *count < 0)
            throw BadParameterGenericError{ "count", "must not be negative" };

        std::size_t size{ count ? static_cast<std::size_t>(*count) : defaultPageSize };
        if (size > maxPageSize)
            size = maxPageSize;

        return db::Range{ offset ? static_cast<std::size_t>(*offset) : 0, size };
    }

    /// Where the next page starts and whether there is one.
    struct DedupedPageResult
    {
        std::size_t nextOffset{};
        bool moreResults{};
    };

    /// Fills \p out with up to \p requestedCount items that are unique by \p keyOf, scanning
    /// the underlying list in batches of \p scanBatchSize from \p initialOffset.
    ///
    /// \p fetchBatch(offset, size, visit) must call visit(item) for the items at
    /// [offset, offset + size). \p replaces(current, candidate) decides whether a later item
    /// with the same key takes the place of the one already kept.
    ///
    /// nextOffset counts only the items actually consumed: once the page is full, the rest of
    /// the batch was fetched but never looked at, and skipping over it would lose those
    /// tracks for good (the defect this replaces advanced by the whole batch).
    template<typename Item, typename FetchBatch, typename KeyOf, typename Replaces>
    DedupedPageResult collectDedupedPage(std::size_t initialOffset, std::size_t requestedCount, std::size_t scanBatchSize, std::size_t maxScanCount, FetchBatch&& fetchBatch, KeyOf&& keyOf, Replaces&& replaces, std::vector<Item>& out)
    {
        std::unordered_map<std::string, std::size_t> indexByKey;
        std::size_t consumed{};
        std::size_t scanned{};
        std::size_t scanOffset{ initialOffset };
        bool moreResults{};

        while (out.size() < requestedCount && scanned < maxScanCount)
        {
            std::size_t batchScanned{};
            std::size_t batchConsumed{};
            fetchBatch(scanOffset, scanBatchSize, [&](const Item& item) {
                ++batchScanned;
                if (out.size() >= requestedCount)
                    return;

                ++batchConsumed;
                const auto [it, inserted]{ indexByKey.try_emplace(keyOf(item), out.size()) };
                if (inserted)
                    out.push_back(item);
                else if (replaces(out[it->second], item))
                    out[it->second] = item;
            });

            scanned += batchScanned;
            consumed += batchConsumed;
            scanOffset += batchScanned;

            // A full batch may have more behind it; a batch the page filled part-way through
            // certainly does.
            moreResults = batchScanned >= scanBatchSize || batchConsumed < batchScanned;

            if (batchScanned < scanBatchSize)
                break;
        }

        return DedupedPageResult{ .nextOffset = initialOffset + consumed, .moreResults = moreResults };
    }
} // namespace lms::api::subsonic::spotifyPaging
