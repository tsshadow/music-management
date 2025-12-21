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

#include "core/media/ImageType.hpp"

namespace lms::core::media
{
    core::LiteralString imageTypeToString(ImageType type)
    {
        switch (type)
        {
        case ImageType::Other:
            return "Other";
        case ImageType::FileIcon:
            return "FileIcon";
        case ImageType::OtherFileIcon:
            return "OtherFileIcon";
        case ImageType::FrontCover:
            return "FrontCover";
        case ImageType::BackCover:
            return "BackCover";
        case ImageType::LeafletPage:
            return "LeafletPage";
        case ImageType::Media:
            return "Media";
        case ImageType::LeadArtist:
            return "LeadArtist";
        case ImageType::Artist:
            return "Artist";
        case ImageType::Conductor:
            return "Conductor";
        case ImageType::Band:
            return "Band";
        case ImageType::Composer:
            return "Composer";
        case ImageType::Lyricist:
            return "Lyricist";
        case ImageType::RecordingLocation:
            return "RecordingLocation";
        case ImageType::DuringRecording:
            return "DuringRecording";
        case ImageType::DuringPerformance:
            return "DuringPerformance";
        case ImageType::MovieScreenCapture:
            return "MovieScreenCapture";
        case ImageType::ColouredFish:
            return "ColouredFish";
        case ImageType::Illustration:
            return "Illustration";
        case ImageType::BandLogo:
            return "BandLogo";
        case ImageType::PublisherLogo:
            return "PublisherLogo";
        case ImageType::Unknown:
            break;
        }

        return "Unknown";
    }
} // namespace lms::core::media