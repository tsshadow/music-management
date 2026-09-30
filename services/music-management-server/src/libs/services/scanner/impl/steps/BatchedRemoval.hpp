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
#include <deque>
#include <span>
#include <vector>

namespace lms::scanner
{
    // Removes the ids in `pending` one write batch of at most `batchSize` at a time and returns
    // how many it handed to `removeBatch`.
    //
    // `removeBatch(std::span<const IdType>)` opens and commits its own write transaction.
    // `afterBatch()` runs after every batch, with that transaction committed and none open --
    // the moment ScanStepCheckForRemovedFiles lets a priority pass through (bug report 136).
    // It may add ids to `pending`; they are removed in the same call.
    //
    // With `fullBatchesOnly`, a remainder smaller than `batchSize` is left for later.
    //
    // Why this exists: removing a row is not cheap. On production an image row costs about
    // 0.2 s, because deleting it cascades to artwork and each artwork delete sets
    // preferred_artwork_id to NULL in track, release, medium and artist, none of which has an
    // index on that column. When a library scan finds twenty thousand of them, the removal used
    // to run as one block before the priority pass could start -- half an hour in which no
    // announced folder was read.
    template<typename IdType, typename RemoveBatch, typename AfterBatch>
    std::size_t removeInWriteBatches(std::deque<IdType>& pending, std::size_t batchSize, bool fullBatchesOnly, RemoveBatch&& removeBatch, AfterBatch&& afterBatch)
    {
        std::size_t removedCount{};
        std::vector<IdType> batch;
        batch.reserve(batchSize);

        while (fullBatchesOnly ? pending.size() >= batchSize : !pending.empty())
        {
            batch.clear();
            while (!pending.empty() && batch.size() < batchSize)
            {
                batch.push_back(pending.front());
                pending.pop_front();
            }

            removeBatch(std::span<const IdType>{ batch });
            removedCount += batch.size();

            afterBatch();
        }

        return removedCount;
    }
} // namespace lms::scanner
