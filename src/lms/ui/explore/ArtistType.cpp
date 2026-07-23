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

#include "ArtistType.hpp"

#include "core/Utils.hpp"

namespace lms::core::stringUtils
{
    template<>
    std::optional<lms::ui::ArtistType> readAs(std::string_view str)
    {
        if (str == "all")
            return lms::ui::AllArtistsTag{};
        if (str == "release")
            return lms::ui::ReleaseArtistsTag{};

        using UnderlyingType = std::underlying_type_t<lms::db::TrackArtistLinkType>;
        std::optional<UnderlyingType> underlyingValue{ readAs<UnderlyingType>(str) };
        if (!underlyingValue)
            return std::nullopt;

        return lms::db::TrackArtistLinkType{ *underlyingValue };
    }
} // namespace lms::core::stringUtils

namespace std
{
    std::string to_string(const lms::ui::ArtistType& artistType)
    {
        std::string res;
        std::visit(lms::core::utils::overloads{
                       [&](lms::ui::AllArtistsTag) { res = "all"; },
                       [&](lms::ui::ReleaseArtistsTag) { res = "release"; },
                       [&](lms::db::TrackArtistLinkType linkType) { res = std::to_string(static_cast<std::underlying_type_t<lms::db::TrackArtistLinkType>>(linkType)); } },
                   artistType);

        return res;
    }
} // namespace std
