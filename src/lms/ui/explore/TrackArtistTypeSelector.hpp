/*
 * Copyright (C) 2026 Emeric Poupon
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

#include "core/EnumSet.hpp"

#include "database/objects/Types.hpp"

#include "DropDownMenuSelector.hpp"

namespace lms::ui
{
    class TrackArtistTypeSelector : public DropDownMenuSelector<std::optional<db::TrackArtistLinkType>>
    {
    public:
        TrackArtistTypeSelector(std::optional<db::TrackArtistLinkType> defaultRole, core::EnumSet<db::TrackArtistLinkType> types);
    };
} // namespace lms::ui
