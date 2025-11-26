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

#include <Wt/WDate.h>

#include "core/LiteralString.hpp"
#include "core/TaggedType.hpp"

namespace lms::db
{
    // For enums that have explicit values, never change enum values as they are stored in database.
    // => only add new values or remove unused values, do not recycle values.

    struct YearRange
    {
        int begin{};
        int end{};
    };

    struct FileInfo
    {
        Wt::WDateTime lastWrittenTime;
        std::size_t scanVersion{};
    };

    enum class ArtistSortMethod
    {
        None,
        Id,
        Name,
        SortName,
        Random,
        LastWrittenDesc,
        AddedDesc,
        StarredDateDesc,
    };

    enum class ClusterSortMethod
    {
        None,
        Name,
    };

    enum class DirectorySortMethod
    {
        None,
        Name,
    };

    using ImageHashType = core::TaggedType<class ImageHash, std::uint64_t>;

    enum class LabelSortMethod
    {
        None,
        Name,
    };

    enum class MediumSortMethod
    {
        None,
        PositionAsc,
    };

    enum class PodcastEpisodeSortMode
    {
        None,
        PubDateAsc,
        PubDateDesc,
    };

    enum class ReleaseSortMethod
    {
        None,
        Id,
        Name,
        SortName,
        ArtistNameThenName,
        DateAsc,
        DateDesc,
        OriginalDate,
        OriginalDateDesc,
        Random,
        LastWrittenDesc,
        AddedDesc,
        StarredDateDesc,
    };

    enum class ReleaseTypeSortMethod
    {
        None,
        Name,
    };

    enum class TrackArtistLinkSortMethod
    {
        None,
        OriginalDateDesc,
    };

    enum class TrackEmbeddedImageSortMethod
    {
        None,
        SizeDesc,
        TrackNumberThenSizeDesc,
        DiscNumberThenTrackNumberThenSizeDesc,
        TrackListIndexAscThenSizeDesc,
    };

    enum class TrackListSortMethod
    {
        None,
        Name,
        LastModifiedDesc,
    };

    enum class TrackSortMethod
    {
        None,
        Id,
        Random,
        LastWrittenDesc,
        AddedDesc,
        StarredDateDesc,
        AbsoluteFilePath,
        Name,
        DateDescAndRelease,
        OriginalDateDescAndRelease,
        Release,   // order by disc/track number
        TrackList, // order by asc order in tracklist
        TrackNumber,
    };

    enum class TrackLyricsSortMethod
    {
        None,
        ExternalFirst,
        EmbeddedFirst,
    };

    enum class ImageType
    {
        Unknown = 0,
        Other = 1,
        FileIcon = 2,
        OtherFileIcon = 3,
        FrontCover = 4,
        BackCover = 5,
        LeafletPage = 6,
        Media = 7,
        LeadArtist = 8,
        Artist = 9,
        Conductor = 10,
        Band = 11,
        Composer = 12,
        Lyricist = 13,
        RecordingLocation = 14,
        DuringRecording = 15,
        DuringPerformance = 16,
        MovieScreenCapture = 17,
        ColouredFish = 18,
        Illustration = 19,
        BandLogo = 20,
        PublisherLogo = 21
    };

    enum class TrackArtistLinkType
    {
        Artist = 0, // regular track artist
        Arranger = 1,
        Composer = 2,
        Conductor = 3,
        Lyricist = 4,
        Mixer = 5,
        Performer = 6,
        Producer = 7,
        ReleaseArtist = 8,
        Remixer = 9,
        Writer = 10,
    };

    core::LiteralString trackArtistLinkTypeToString(TrackArtistLinkType type);

    // User selectable transcoding output formats
    enum class TranscodingOutputFormat
    {
        MP3 = 1,
        OGG_OPUS = 2,
        OGG_VORBIS = 3,
        WEBM_VORBIS = 4,
        MATROSKA_OPUS = 5,
    };

    using Bitrate = std::uint32_t;
    void visitAllowedAudioBitrates(std::function<void(Bitrate)>);
    bool isAudioBitrateAllowed(Bitrate bitrate);

    using Rating = int;

    enum class ScrobblingBackend
    {
        Internal = 0,
        ListenBrainz = 1,
    };

    enum class FeedbackBackend
    {
        Internal = 0,
        ListenBrainz = 1,
    };

    enum class SyncState
    {
        PendingAdd = 0,
        Synchronized = 1,
        PendingRemove = 2,
    };

    enum class UserType
    {
        REGULAR = 0,
        ADMIN = 1,
        DEMO = 2,
    };

    enum class UITheme
    {
        Light = 0,
        Dark = 1,
    };

    enum class SubsonicArtistListMode
    {
        AllArtists = 0,
        ReleaseArtists = 1,
        TrackArtists = 2,
    };

    enum class TrackListType
    {
        PlayList = 0, // user controlled playlists
        Internal = 1, // internal usage (current playqueue, history, ...)
    };

    enum class Advisory
    {
        UnSet = 0,
        Unknown = 1,
        Clean = 2,
        Explicit = 3,
    };

    enum class ContainerType
    {
        Unknown = 0,

        AIFF = 1,
        APE = 2,
        ASF = 3,
        DSF = 4,
        FLAC = 5,
        MP4 = 6,
        MPC = 7,
        MPEG = 8,
        Ogg = 9,
        Shorten = 10,
        TrueAudio = 11,
        WAV = 12,
        WavPack = 13,
    };

    enum class CodecType
    {
        Unknown = 0,

        AAC = 1,
        AC3 = 2,
        ALAC = 3,
        APE = 4,
        DSD = 5,
        EAC3 = 6,
        FLAC = 7,
        MP3 = 8,
        MP4ALS = 9,
        MPC7 = 10,
        MPC8 = 11,
        Opus = 12,
        PCM = 13,
        Shorten = 14,
        TrueAudio = 15,
        Vorbis = 16,
        WavPack = 17,
        WMA1 = 18,
        WMA2 = 19,
        WMA9Pro = 20,
        WMA9Lossless = 21,
    };
} // namespace lms::db
