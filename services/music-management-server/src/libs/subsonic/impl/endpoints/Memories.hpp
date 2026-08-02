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

#pragma once

#include "../RequestContext.hpp"
#include "../SubsonicResponse.hpp"

#include "database/objects/Track.hpp"

#include <cstddef>
#include <optional>
#include <string_view>
#include <vector>

#include <Wt/WDate.h>

namespace lms::api::subsonic
{
    Response handleGetMemories(RequestContext& ctx);

    namespace memories
    {
        /** One track that qualified as a memory, with the facts the grouping needs. */
        struct DatedTrack
        {
            db::TrackId id;
            int year{};   // effective release year
            bool exact{}; // released on exactly the requested month and day
        };

        /** One year's worth of memories. */
        struct Group
        {
            int year{};
            bool exact{}; // at least one track in this group is an exact date match
            std::vector<db::TrackId> trackIds;
        };

        /**
         * Groups tracks per release year, newest year first, keeping at most maxPerYear tracks in
         * each group.
         *
         * Exact date matches are placed before window matches inside a group, so truncation can
         * never drop an exact match while a near miss survives.
         */
        std::vector<Group> groupByYear(const std::vector<DatedTrack>& tracks, std::size_t maxPerYear);

        inline constexpr std::size_t defaultWindowDays{ 3 };
        inline constexpr std::size_t maxWindowDays{ 14 };
        inline constexpr std::size_t defaultMaxPerYear{ 30 };
        inline constexpr std::size_t maxMaxPerYear{ 200 };

        /**
         * An absurd window or page size is a client being sloppy, not a client being wrong, so it
         * is clamped into range rather than rejected.
         */
        std::size_t clampWindowDays(std::size_t windowDays);
        std::size_t clampMaxPerYear(std::size_t maxPerYear);

        /** Parses a yyyy-MM-dd date. An unparseable date is a client error, hence the optional. */
        std::optional<Wt::WDate> parseIsoDate(std::string_view date);
    } // namespace memories
} // namespace lms::api::subsonic
