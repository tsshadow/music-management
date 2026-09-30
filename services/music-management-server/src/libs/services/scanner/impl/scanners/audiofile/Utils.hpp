
/*
 * Copyright (C) 2016 Emeric Poupon
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

#include <optional>
#include <string_view>

#include <Wt/WDate.h>

#include "types/TrackMetadata.hpp"

namespace lms::scanner::utils
{
    Wt::WDate parseDate(std::string_view dateStr);
    std::optional<int> parseYear(std::string_view yearStr);

    // A BPM tag as an integer tempo. ID3 TBPM is text and taggers write "150", "150.0" or,
    // with a decimal comma, "150,5"; MP4 tmpo arrives as an integer already. The value is
    // rounded half up. Anything that is not a number, or falls outside [minBpm, maxBpm],
    // is no tempo at all: a 0 or a mis-parsed 1500 is noise, not a very slow or fast song.
    inline constexpr int minBpm{ 40 };
    inline constexpr int maxBpm{ 500 };
    std::optional<int> parseBpm(std::string_view bpmStr);

    struct PerformerArtist
    {
        Artist artist;
        std::string role;
    };

    // format is "artist name (role)"
    PerformerArtist extractPerformerAndRole(std::string_view entry);
} // namespace lms::scanner::utils
