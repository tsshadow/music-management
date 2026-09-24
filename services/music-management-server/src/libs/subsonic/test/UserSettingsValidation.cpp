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

#include <string>

#include <gtest/gtest.h>

#include "endpoints/UserSettingsValidation.hpp"

namespace lms::api::subsonic::tests
{
    using namespace userSettings;

    // feedbackBackend=7 used to be stored as-is; the user's next rating then looked up a
    // backend that does not exist and crashed the whole server.
    TEST(UserSettingsValidation, feedbackBackendAcceptsOnlyRegisteredBackends)
    {
        EXPECT_EQ(toFeedbackBackend(0), db::FeedbackBackend::Internal);
        EXPECT_EQ(toFeedbackBackend(1), db::FeedbackBackend::ListenBrainz);
        EXPECT_EQ(toFeedbackBackend(2), db::FeedbackBackend::MusicManagement);

        EXPECT_FALSE(toFeedbackBackend(-1));
        EXPECT_FALSE(toFeedbackBackend(3));
        EXPECT_FALSE(toFeedbackBackend(7));
        EXPECT_FALSE(toFeedbackBackend(2147483647));
    }

    TEST(UserSettingsValidation, scrobblingBackendAcceptsOnlyRegisteredBackends)
    {
        EXPECT_EQ(toScrobblingBackend(0), db::ScrobblingBackend::Internal);
        EXPECT_EQ(toScrobblingBackend(1), db::ScrobblingBackend::ListenBrainz);

        EXPECT_FALSE(toScrobblingBackend(-1));
        EXPECT_FALSE(toScrobblingBackend(2));
        EXPECT_FALSE(toScrobblingBackend(99));
    }

    TEST(UserSettingsValidation, transcodingFormatSkipsRetiredValues)
    {
        EXPECT_EQ(toTranscodingOutputFormat(1), db::TranscodingOutputFormat::MP3);
        EXPECT_EQ(toTranscodingOutputFormat(2), db::TranscodingOutputFormat::OGG_OPUS);
        EXPECT_EQ(toTranscodingOutputFormat(3), db::TranscodingOutputFormat::OGG_VORBIS);

        EXPECT_FALSE(toTranscodingOutputFormat(0));
        EXPECT_FALSE(toTranscodingOutputFormat(4)); // WEBM_VORBIS, retired
        EXPECT_FALSE(toTranscodingOutputFormat(5)); // MATROSKA_OPUS, retired
    }

    TEST(UserSettingsValidation, enumRangesMatchTheEnums)
    {
        EXPECT_EQ(toSubsonicArtistListMode(0), db::SubsonicArtistListMode::AllArtists);
        EXPECT_EQ(toSubsonicArtistListMode(2), db::SubsonicArtistListMode::TrackArtists);
        EXPECT_FALSE(toSubsonicArtistListMode(-1));
        EXPECT_FALSE(toSubsonicArtistListMode(3));

        EXPECT_EQ(toReleaseSortMethod(0), db::ReleaseSortMethod::None);
        EXPECT_EQ(toReleaseSortMethod(8), db::ReleaseSortMethod::OriginalDateDesc); // the web player's default
        EXPECT_EQ(toReleaseSortMethod(static_cast<int>(db::ReleaseSortMethod::Relevance)), db::ReleaseSortMethod::Relevance);
        EXPECT_FALSE(toReleaseSortMethod(-1));
        EXPECT_FALSE(toReleaseSortMethod(static_cast<int>(db::ReleaseSortMethod::Relevance) + 1));
    }

    // Values past the enum were inserted into an EnumSet bitmask, which is undefined behaviour
    // for anything beyond its width; 8 is the retired ReleaseArtist slot.
    TEST(UserSettingsValidation, trackArtistLinkTypeRejectsUnknownValues)
    {
        EXPECT_EQ(toTrackArtistLinkType(0), db::TrackArtistLinkType::Artist);
        EXPECT_EQ(toTrackArtistLinkType(2), db::TrackArtistLinkType::Composer);
        EXPECT_EQ(toTrackArtistLinkType(6), db::TrackArtistLinkType::Performer);
        EXPECT_EQ(toTrackArtistLinkType(10), db::TrackArtistLinkType::Writer);

        EXPECT_FALSE(toTrackArtistLinkType(-1));
        EXPECT_FALSE(toTrackArtistLinkType(8));
        EXPECT_FALSE(toTrackArtistLinkType(11));
        EXPECT_FALSE(toTrackArtistLinkType(64));
    }

    // Tokens are looked up by value across every user; a short one collides and can be guessed.
    TEST(UserSettingsValidation, subsonicTokenNeedsAMinimumLength)
    {
        EXPECT_EQ(minSubsonicTokenLength, 16);
        EXPECT_FALSE(isAcceptableSubsonicToken("abc"));
        EXPECT_FALSE(isAcceptableSubsonicToken(std::string(15, 'x')));
        EXPECT_TRUE(isAcceptableSubsonicToken(std::string(16, 'x')));
        EXPECT_TRUE(isAcceptableSubsonicToken("0123456789abcdef0123456789abcdef"));
    }
} // namespace lms::api::subsonic::tests
