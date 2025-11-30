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

#include "Types.hpp"

namespace lms::db::detail
{
    std::optional<core::media::ContainerType> getMediaContainerType(db::detail::ContainerType container)
    {
        switch (container)
        {
        case ContainerType::AIFF:
            return core::media::ContainerType::AIFF;
        case ContainerType::APE:
            return core::media::ContainerType::APE;
        case ContainerType::ASF:
            return core::media::ContainerType::ASF;
        case ContainerType::DSF:
            return core::media::ContainerType::DSF;
        case ContainerType::FLAC:
            return core::media::ContainerType::FLAC;
        case ContainerType::MP4:
            return core::media::ContainerType::MP4;
        case ContainerType::MPC:
            return core::media::ContainerType::MPC;
        case ContainerType::MPEG:
            return core::media::ContainerType::MPEG;
        case ContainerType::Ogg:
            return core::media::ContainerType::Ogg;
        case ContainerType::Shorten:
            return core::media::ContainerType::Shorten;
        case ContainerType::TrueAudio:
            return core::media::ContainerType::TrueAudio;
        case ContainerType::WAV:
            return core::media::ContainerType::WAV;
        case ContainerType::WavPack:
            return core::media::ContainerType::WavPack;

        case ContainerType::Unknown:
            break;
        }

        return std::nullopt;
    }

    db::detail::ContainerType getDbContainerType(core::media::ContainerType container)
    {
        switch (container)
        {
        case core::media::ContainerType::AIFF:
            return ContainerType::AIFF;
        case core::media::ContainerType::APE:
            return ContainerType::APE;
        case core::media::ContainerType::ASF:
            return ContainerType::ASF;
        case core::media::ContainerType::DSF:
            return ContainerType::DSF;
        case core::media::ContainerType::FLAC:
            return ContainerType::FLAC;
        case core::media::ContainerType::MP4:
            return ContainerType::MP4;
        case core::media::ContainerType::MPC:
            return ContainerType::MPC;
        case core::media::ContainerType::MPEG:
            return ContainerType::MPEG;
        case core::media::ContainerType::Ogg:
            return ContainerType::Ogg;
        case core::media::ContainerType::Shorten:
            return ContainerType::Shorten;
        case core::media::ContainerType::TrueAudio:
            return ContainerType::TrueAudio;
        case core::media::ContainerType::WAV:
            return ContainerType::WAV;
        case core::media::ContainerType::WavPack:
            return ContainerType::WavPack;
        }

        return ContainerType::Unknown;
    }

    std::optional<core::media::CodecType> getMediaCodecType(db::detail::CodecType codec)
    {
        switch (codec)
        {
        case CodecType::AAC:
            return core::media::CodecType::AAC;
        case CodecType::AC3:
            return core::media::CodecType::AC3;
        case CodecType::ALAC:
            return core::media::CodecType::ALAC;
        case CodecType::APE:
            return core::media::CodecType::APE;
        case CodecType::DSD:
            return core::media::CodecType::DSD;
        case CodecType::EAC3:
            return core::media::CodecType::EAC3;
        case CodecType::FLAC:
            return core::media::CodecType::FLAC;
        case CodecType::MP3:
            return core::media::CodecType::MP3;
        case CodecType::MP4ALS:
            return core::media::CodecType::MP4ALS;
        case CodecType::MPC7:
            return core::media::CodecType::MPC7;
        case CodecType::MPC8:
            return core::media::CodecType::MPC8;
        case CodecType::Opus:
            return core::media::CodecType::Opus;
        case CodecType::PCM:
            return core::media::CodecType::PCM;
        case CodecType::Shorten:
            return core::media::CodecType::Shorten;
        case CodecType::TrueAudio:
            return core::media::CodecType::TrueAudio;
        case CodecType::Vorbis:
            return core::media::CodecType::Vorbis;
        case CodecType::WavPack:
            return core::media::CodecType::WavPack;
        case CodecType::WMA1:
            return core::media::CodecType::WMA1;
        case CodecType::WMA2:
            return core::media::CodecType::WMA2;
        case CodecType::WMA9Pro:
            return core::media::CodecType::WMA9Pro;
        case CodecType::WMA9Lossless:
            return core::media::CodecType::WMA9Lossless;

        case CodecType::Unknown:
            break;
        }

        return std::nullopt;
    }

    db::detail::CodecType getDbCodecType(core::media::CodecType codec)
    {
        switch (codec)
        {
        case core::media::CodecType::AAC:
            return CodecType::AAC;
        case core::media::CodecType::AC3:
            return CodecType::AC3;
        case core::media::CodecType::ALAC:
            return CodecType::ALAC;
        case core::media::CodecType::APE:
            return CodecType::APE;
        case core::media::CodecType::DSD:
            return CodecType::DSD;
        case core::media::CodecType::EAC3:
            return CodecType::EAC3;
        case core::media::CodecType::FLAC:
            return CodecType::FLAC;
        case core::media::CodecType::MP3:
            return CodecType::MP3;
        case core::media::CodecType::MP4ALS:
            return CodecType::MP4ALS;
        case core::media::CodecType::MPC7:
            return CodecType::MPC7;
        case core::media::CodecType::MPC8:
            return CodecType::MPC8;
        case core::media::CodecType::Opus:
            return CodecType::Opus;
        case core::media::CodecType::PCM:
            return CodecType::PCM;
        case core::media::CodecType::Shorten:
            return CodecType::Shorten;
        case core::media::CodecType::TrueAudio:
            return CodecType::TrueAudio;
        case core::media::CodecType::Vorbis:
            return CodecType::Vorbis;
        case core::media::CodecType::WavPack:
            return CodecType::WavPack;
        case core::media::CodecType::WMA1:
            return CodecType::WMA1;
        case core::media::CodecType::WMA2:
            return CodecType::WMA2;
        case core::media::CodecType::WMA9Pro:
            return CodecType::WMA9Pro;
        case core::media::CodecType::WMA9Lossless:
            return CodecType::WMA9Lossless;
        }

        return CodecType::Unknown;
    }

    core::media::ImageType getMediaImageType(db::detail::ImageType type)
    {
        switch (type)
        {
        case db::detail::ImageType::Unknown:
            return core::media::ImageType::Unknown;
        case db::detail::ImageType::Other:
            return core::media::ImageType::Other;
        case db::detail::ImageType::FileIcon:
            return core::media::ImageType::FileIcon;
        case db::detail::ImageType::OtherFileIcon:
            return core::media::ImageType::OtherFileIcon;
        case db::detail::ImageType::FrontCover:
            return core::media::ImageType::FrontCover;
        case db::detail::ImageType::BackCover:
            return core::media::ImageType::BackCover;
        case db::detail::ImageType::LeafletPage:
            return core::media::ImageType::LeafletPage;
        case db::detail::ImageType::Media:
            return core::media::ImageType::Media;
        case db::detail::ImageType::LeadArtist:
            return core::media::ImageType::LeadArtist;
        case db::detail::ImageType::Artist:
            return core::media::ImageType::Artist;
        case db::detail::ImageType::Conductor:
            return core::media::ImageType::Conductor;
        case db::detail::ImageType::Band:
            return core::media::ImageType::Band;
        case db::detail::ImageType::Composer:
            return core::media::ImageType::Composer;
        case db::detail::ImageType::Lyricist:
            return core::media::ImageType::Lyricist;
        case db::detail::ImageType::RecordingLocation:
            return core::media::ImageType::RecordingLocation;
        case db::detail::ImageType::DuringRecording:
            return core::media::ImageType::DuringRecording;
        case db::detail::ImageType::DuringPerformance:
            return core::media::ImageType::DuringPerformance;
        case db::detail::ImageType::MovieScreenCapture:
            return core::media::ImageType::MovieScreenCapture;
        case db::detail::ImageType::ColouredFish:
            return core::media::ImageType::ColouredFish;
        case db::detail::ImageType::Illustration:
            return core::media::ImageType::Illustration;
        case db::detail::ImageType::BandLogo:
            return core::media::ImageType::BandLogo;
        case db::detail::ImageType::PublisherLogo:
            return core::media::ImageType::PublisherLogo;
        }

        return core::media::ImageType::Unknown;
    }

    db::detail::ImageType getDbImageType(core::media::ImageType type)
    {
        switch (type)
        {
        case core::media::ImageType::Unknown:
            return db::detail::ImageType::Unknown;
        case core::media::ImageType::Other:
            return db::detail::ImageType::Other;
        case core::media::ImageType::FileIcon:
            return db::detail::ImageType::FileIcon;
        case core::media::ImageType::OtherFileIcon:
            return db::detail::ImageType::OtherFileIcon;
        case core::media::ImageType::FrontCover:
            return db::detail::ImageType::FrontCover;
        case core::media::ImageType::BackCover:
            return db::detail::ImageType::BackCover;
        case core::media::ImageType::LeafletPage:
            return db::detail::ImageType::LeafletPage;
        case core::media::ImageType::Media:
            return db::detail::ImageType::Media;
        case core::media::ImageType::LeadArtist:
            return db::detail::ImageType::LeadArtist;
        case core::media::ImageType::Artist:
            return db::detail::ImageType::Artist;
        case core::media::ImageType::Conductor:
            return db::detail::ImageType::Conductor;
        case core::media::ImageType::Band:
            return db::detail::ImageType::Band;
        case core::media::ImageType::Composer:
            return db::detail::ImageType::Composer;
        case core::media::ImageType::Lyricist:
            return db::detail::ImageType::Lyricist;
        case core::media::ImageType::RecordingLocation:
            return db::detail::ImageType::RecordingLocation;
        case core::media::ImageType::DuringRecording:
            return db::detail::ImageType::DuringRecording;
        case core::media::ImageType::DuringPerformance:
            return db::detail::ImageType::DuringPerformance;
        case core::media::ImageType::MovieScreenCapture:
            return db::detail::ImageType::MovieScreenCapture;
        case core::media::ImageType::ColouredFish:
            return db::detail::ImageType::ColouredFish;
        case core::media::ImageType::Illustration:
            return db::detail::ImageType::Illustration;
        case core::media::ImageType::BandLogo:
            return db::detail::ImageType::BandLogo;
        case core::media::ImageType::PublisherLogo:
            return db::detail::ImageType::PublisherLogo;
        }

        return db::detail::ImageType::Unknown;
    }
} // namespace lms::db::detail