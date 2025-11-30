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

#include "core/media/MimeType.hpp"

namespace lms::core::media
{
    core::LiteralString getMimeType(ContainerType container, CodecType codec)
    {
        switch (container)
        {
        case ContainerType::AIFF:
            return "audio/x-aiff";
        case ContainerType::APE:
            return "audio/x-monkeys-audio";
        case ContainerType::ASF:
            return "audio/x-ms-wma";
        case ContainerType::DSF:
            return "audio/x-dsd-dsf";
        case ContainerType::FLAC:
            return "audio/flac";
        case ContainerType::MP4:
            switch (codec)
            {
            case CodecType::AAC:
                return "audio/mp4; codecs=\"mp4a.40.2\"";
            case CodecType::ALAC:
                return "audio/mp4; codecs=\"alac\"";
            case CodecType::MP4ALS:
                return "audio/mp4; codecs=\"mp4als\"";
            default:
                return "audio/mp4";
            }

        case ContainerType::MPC:
            return "audio/x-musepack";
        case ContainerType::MPEG:
            return "audio/mpeg";
        case ContainerType::Ogg:
            switch (codec)
            {
            case CodecType::Opus:
                return "audio/opus";
            case CodecType::Vorbis:
                return "audio/ogg; codecs=\"vorbis\"";
            case CodecType::FLAC:
                return "audio/ogg; codecs=\"flac\"";
            default:
                return "audio/ogg";
            }

        case ContainerType::Shorten:
            return "audio/x-shn";
        case ContainerType::TrueAudio:
            return "audio/x-tta";
        case ContainerType::WAV:
            return "audio/wav";
        case ContainerType::WavPack:
            return "audio/x-wavpack";
        }

        return "application/octet-stream";
    }
} // namespace lms::core::media