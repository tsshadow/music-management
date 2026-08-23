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
#include <string>
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
            int year{};            // effective release year
            bool exact{};          // released on exactly the requested month and day
            bool favourite{};      // rated five stars by the requesting user
            std::size_t listens{}; // how often the requesting user played it
            int source{};          // how deliberate the release is, see sourceRank
        };

        /**
         * How deliberate a release is, read from its label names.
         *
         * Most of a memory year carries neither a rating nor a listen, so without this the order of
         * such a year would be arbitrary. The label is the one thing the library does know about
         * every track, because the scanner stores the publisher tag as a label -- including for the
         * downloaders, which write the platform there. That makes "which label" double as "where did
         * this come from", and a release on a label is the most deliberate thing in a year.
         *
         * Highest first:
         *   6  a real label
         *   5  no label at all -- often a release whose publisher was never matched
         *   4  Free&None -- music, but a giveaway rather than a label release
         *   3  Soundcloud
         *   2  Youtube
         *   1  Telegram
         *   0  TODO -- the import pile, not a release at all
         *
         * Leading underscores and capitalisation are ignored: the same placeholder exists with two
         * and with three underscores, and the tag's case is whatever wrote it.
         *
         * @param labelNames - The label names of the track's release; empty when it has none.
         * @returns The rank, higher being more deliberate.
         */
        int sourceRank(const std::vector<std::string>& labelNames);

        /** One year's worth of memories. */
        struct Group
        {
            int year{};
            bool exact{};        // at least one track in this group is an exact date match
            std::size_t total{}; // the year's full size, before maxPerYear truncated it
            std::vector<db::TrackId> trackIds;
        };

        /**
         * Groups tracks per release year, newest year first, keeping at most maxPerYear tracks in
         * each group.
         *
         * A year is ordered by what the listener values most -- a five-star favourite first, then
         * the listen count -- so that a client showing only the head of a group shows its best
         * tracks rather than whichever ones the query happened to return first. Tracks the listener
         * treats identically are separated by the date, which keeps the original guarantee that
         * truncation can never drop an exact anniversary while a near miss survives.
         *
         * `total` reports the year before truncation: a count is a fact about the year, not about
         * the page size, and reporting the page size makes every large year claim to be exactly as
         * big as the limit.
         */
        std::vector<Group> groupByYear(const std::vector<DatedTrack>& tracks, std::size_t maxPerYear);

        inline constexpr std::size_t defaultWindowDays{ 3 };
        inline constexpr std::size_t maxWindowDays{ 14 };
        inline constexpr std::size_t defaultMaxPerYear{ 30 };

        // High enough that a client asking for one year gets all of it: the biggest year in a real
        // library sits in the hundreds, and a client that wants the whole thing asks for one year
        // rather than for every year at once.
        inline constexpr std::size_t maxMaxPerYear{ 1000 };

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
