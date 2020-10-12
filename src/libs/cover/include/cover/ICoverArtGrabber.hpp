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

#include <cstddef>
#include <filesystem>
#include <memory>
#include <string_view>

#include "database/Types.hpp"
#include "cover/ICoverArt.hpp"

namespace Database
{
	class Session;
}

namespace CoverArt
{
	using Width = std::size_t;

	class IGrabber
	{
		public:
			virtual ~IGrabber() = default;

			virtual void			setDefaultCover(const std::filesystem::path& defaultCoverPath) = 0;

			virtual std::unique_ptr<ICoverArt>	getFromTrack(Database::Session& dbSession, Database::IdType trackId, Width width) = 0;
			virtual std::unique_ptr<ICoverArt>	getFromRelease(Database::Session& dbSession, Database::IdType releaseId, Width width) = 0;

			virtual void flushCache() = 0;
	};

	std::unique_ptr<IGrabber> createGrabber(const std::filesystem::path& execPath, std::size_t maxCacheEntries, std::size_t maxFileSize);

} // namespace CoverArt

