/*
 * Copyright (C) 2015 Emeric Poupon
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

#include <algorithm>
#include <cassert>

#include <Wt/WDate.h>

#include "core/Exception.hpp"

namespace lms::db
{
    class Exception : public core::LmsException
    {
    public:
        using LmsException::LmsException;
    };

    // Caution: do not change enum values if they are set!

    // Request:
    // 	  size = 0 => means we don't want data
    // Response (via RangeResults)
    //    size => results size
    struct Range
    {
        std::size_t offset{};
        std::size_t size{};

        bool operator==(const Range& rhs) const { return offset == rhs.offset && size == rhs.size; }
    };

    // Func must return true to continue iterating
    template<typename Func>
    void foreachSubRange(Range range, std::size_t subRangeSize, Func&& func)
    {
        assert(subRangeSize > 0);

        Range subRange{ range.offset, std::min(range.size, subRangeSize) };
        while (subRange.size > 0)
        {
            if (!func(subRange))
                break;

            subRange.offset += subRange.size;
            subRange.size = std::min(subRangeSize, range.size - (subRange.offset - range.offset));
        }
    }

    template<typename T>
    struct RangeResults
    {
        Range range;
        std::vector<T> results;
        bool moreResults{};

        RangeResults getSubRange(Range subRange)
        {
            assert(subRange.offset >= range.offset);

            if (!subRange.size)
                subRange.size = range.size - (subRange.offset - range.offset);

            subRange.offset = std::min(subRange.offset, range.offset + range.size);
            subRange.size = std::min(subRange.size, range.offset + range.size - subRange.offset);

            RangeResults subResults;

            auto itBegin{ std::cbegin(results) + subRange.offset - range.offset };
            auto itEnd{ itBegin + subRange.size };
            subResults.results.reserve(std::distance(itBegin, itEnd));
            std::copy(itBegin, itEnd, std::back_inserter(subResults.results));

            subResults.range = subRange;
            if (subRange.offset + subRange.size == range.offset + range.size)
                subResults.moreResults = moreResults;
            else
                subResults.moreResults = true;

            return subResults;
        }
    };

    struct FileStats
    {
        std::size_t trackCount;
        std::size_t imageCount;
        std::size_t trackLyricsCount;
        std::size_t playListCount;
        std::size_t artistInfoCount;

        std::size_t getTotalFileCount() const { return trackCount + imageCount + trackLyricsCount + playListCount + artistInfoCount; }
    };
} // namespace lms::db
