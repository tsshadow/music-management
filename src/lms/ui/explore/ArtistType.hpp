/*
 * Copyright (C) 2024 Emeric Poupon
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

#include <variant>

#include "core/String.hpp"

#include "database/objects/Types.hpp"

namespace lms::ui
{
    struct AllArtistsTag
    {
        bool operator==(const AllArtistsTag&) const = default;
    };
    struct ReleaseArtistsTag
    {
        bool operator==(const ReleaseArtistsTag&) const = default;
    };

    using ArtistType = std::variant<AllArtistsTag, ReleaseArtistsTag, db::TrackArtistLinkType>;

} // namespace lms::ui

namespace lms::core::stringUtils
{
    template<>
    [[nodiscard]] std::optional<lms::ui::ArtistType> readAs(std::string_view str);
}

namespace std
{
    [[nodiscard]] std::string to_string(const lms::ui::ArtistType& artistType);
};