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

#include "core/media/ContainerType.hpp"

namespace lms::core::media
{
    core::LiteralString containerTypeToString(ContainerType type)
    {
        switch (type)
        {
        case ContainerType::AIFF:
            return "AIFF";
        case ContainerType::APE:
            return "APE";
        case ContainerType::ASF:
            return "ASF";
        case ContainerType::DSF:
            return "DSF";
        case ContainerType::FLAC:
            return "FLAC";
        case ContainerType::MP4:
            return "MP4";
        case ContainerType::MPC:
            return "MPC";
        case ContainerType::MPEG:
            return "MPEG";
        case ContainerType::Ogg:
            return "Ogg";
        case ContainerType::Shorten:
            return "Shorten";
        case ContainerType::TrueAudio:
            return "TrueAudio";
        case ContainerType::WAV:
            return "WAV";
        case ContainerType::WavPack:
            return "WavPack";
        }

        return "Unknown";
    }
} // namespace lms::core::media