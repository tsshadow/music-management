/*
 * Copyright (C) 2025 Emeric Poupon
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

#include <functional>

#include "database/objects/ArtistId.hpp"
#include "database/objects/ReleaseId.hpp"
#include "database/objects/TrackId.hpp"

namespace lms::recommendation
{
    struct Progress
    {
        std::size_t totalElems{};
        std::size_t processedElems{};
    };
    using ProgressCallback = std::function<void(const Progress&)>;

    template<typename IdType>
    using ResultContainer = std::vector<IdType>;

    using ArtistContainer = ResultContainer<db::ArtistId>;
    using ReleaseContainer = ResultContainer<db::ReleaseId>;
    using TrackContainer = ResultContainer<db::TrackId>;

} // namespace lms::recommendation
