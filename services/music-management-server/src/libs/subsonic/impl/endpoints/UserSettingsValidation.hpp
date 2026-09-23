/*
 * Copyright (C) 2026 Teun Schriks
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
#include <optional>
#include <string_view>

#include "database/objects/Types.hpp"

// Range checks for the integer settings /updateUser accepts. Every one of these values is
// stored as an enum and later used as a lookup key (the feedback and scrobbling backends
// index a map of backend instances), so an out-of-range integer must be refused at the door
// instead of being cast blindly: a feedbackBackend of 7 used to crash the whole server on
// the user's next rating.
namespace lms::api::subsonic::userSettings
{
    /// Shortest subsonic token /updateUser accepts. Tokens are looked up by value across all
    /// users, so a short, guessable one both collides with other users and can be brute-forced.
    inline constexpr std::size_t minSubsonicTokenLength{ 16 };

    /// Returns the feedback backend for \p value, or nullopt when no such backend exists.
    constexpr std::optional<db::FeedbackBackend> toFeedbackBackend(int value)
    {
        switch (value)
        {
        case static_cast<int>(db::FeedbackBackend::Internal):
        case static_cast<int>(db::FeedbackBackend::ListenBrainz):
        case static_cast<int>(db::FeedbackBackend::MusicManagement):
            return static_cast<db::FeedbackBackend>(value);
        default:
            return std::nullopt;
        }
    }

    /// Returns the scrobbling backend for \p value, or nullopt when no such backend exists.
    constexpr std::optional<db::ScrobblingBackend> toScrobblingBackend(int value)
    {
        switch (value)
        {
        case static_cast<int>(db::ScrobblingBackend::Internal):
        case static_cast<int>(db::ScrobblingBackend::ListenBrainz):
            return static_cast<db::ScrobblingBackend>(value);
        default:
            return std::nullopt;
        }
    }

    /// Returns the user-selectable transcoding format for \p value, or nullopt otherwise.
    constexpr std::optional<db::TranscodingOutputFormat> toTranscodingOutputFormat(int value)
    {
        switch (value)
        {
        case static_cast<int>(db::TranscodingOutputFormat::MP3):
        case static_cast<int>(db::TranscodingOutputFormat::OGG_OPUS):
        case static_cast<int>(db::TranscodingOutputFormat::OGG_VORBIS):
            return static_cast<db::TranscodingOutputFormat>(value);
        default:
            return std::nullopt;
        }
    }

    /// Returns the artist list mode for \p value, or nullopt when it is out of range.
    constexpr std::optional<db::SubsonicArtistListMode> toSubsonicArtistListMode(int value)
    {
        if (value < static_cast<int>(db::SubsonicArtistListMode::AllArtists) || value > static_cast<int>(db::SubsonicArtistListMode::TrackArtists))
            return std::nullopt;
        return static_cast<db::SubsonicArtistListMode>(value);
    }

    /// Returns the release sort method for \p value, or nullopt when it is out of range.
    constexpr std::optional<db::ReleaseSortMethod> toReleaseSortMethod(int value)
    {
        if (value < static_cast<int>(db::ReleaseSortMethod::None) || value > static_cast<int>(db::ReleaseSortMethod::Relevance))
            return std::nullopt;
        return static_cast<db::ReleaseSortMethod>(value);
    }

    /// Returns the track artist link type for \p value, or nullopt for a value the enum does
    /// not define (including the retired ReleaseArtist slot, 8).
    constexpr std::optional<db::TrackArtistLinkType> toTrackArtistLinkType(int value)
    {
        if (value < static_cast<int>(db::TrackArtistLinkType::Artist) || value > static_cast<int>(db::TrackArtistLinkType::Writer) || value == 8)
            return std::nullopt;
        return static_cast<db::TrackArtistLinkType>(value);
    }

    /// True when \p token is long enough to be stored as a subsonic token. An empty token is
    /// not a token: /updateUser treats it as "clear all tokens" before this check applies.
    constexpr bool isAcceptableSubsonicToken(std::string_view token)
    {
        return token.size() >= minSubsonicTokenLength;
    }
} // namespace lms::api::subsonic::userSettings
