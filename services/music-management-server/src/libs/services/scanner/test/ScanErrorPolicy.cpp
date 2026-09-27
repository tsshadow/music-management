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

#include <gtest/gtest.h>

#include <memory>
#include <system_error>

#include "ScanErrorPolicy.hpp"

namespace lms::scanner::tests
{
    namespace
    {
        ScanOptions scopedTo(std::initializer_list<const char*> directories)
        {
            ScanOptions options;
            for (const char* directory : directories)
                options.scanDirectories.emplace_back(directory);
            return options;
        }

        std::size_t countOf(const ScanErrorCounts& counts, ScanErrorKind kind)
        {
            return counts[static_cast<std::size_t>(kind)];
        }
    } // namespace

    TEST(ScanErrorPolicy, classifiesEveryConcreteErrorType)
    {
        EXPECT_EQ(getScanErrorKind(IOScanError{ "/music/a.mp3", std::make_error_code(std::errc::permission_denied) }), ScanErrorKind::IO);
        EXPECT_EQ(getScanErrorKind(AudioFileScanError{ "/music/a.mp3" }), ScanErrorKind::AudioFile);
        EXPECT_EQ(getScanErrorKind(EmbeddedImageScanError{ "/music/a.mp3", 0, "corrupt" }), ScanErrorKind::EmbeddedImage);
        EXPECT_EQ(getScanErrorKind(NoAudioTrackFoundError{ "/music/a.mp3" }), ScanErrorKind::NoAudioTrack);
        EXPECT_EQ(getScanErrorKind(BadAudioDurationError{ "/music/a.mp3" }), ScanErrorKind::BadAudioDuration);
        EXPECT_EQ(getScanErrorKind(ArtistInfoFileScanError{ "/music/artist.nfo" }), ScanErrorKind::ArtistInfoFile);
        EXPECT_EQ(getScanErrorKind(MissingArtistNameError{ "/music/artist.nfo" }), ScanErrorKind::MissingArtistName);
        EXPECT_EQ(getScanErrorKind(ImageFileScanError{ "/music/cover.jpg", "corrupt" }), ScanErrorKind::ImageFile);
        EXPECT_EQ(getScanErrorKind(LyricsFileScanError{ "/music/a.lrc" }), ScanErrorKind::LyricsFile);
        EXPECT_EQ(getScanErrorKind(PlayListFileScanError{ "/music/a.m3u" }), ScanErrorKind::PlayListFile);
        EXPECT_EQ(getScanErrorKind(PlayListFilePathMissingError{ "/music/a.m3u", "01.mp3" }), ScanErrorKind::PlayListEntryMissing);
        EXPECT_EQ(getScanErrorKind(PlayListFileAllPathesMissingError{ "/music/a.m3u" }), ScanErrorKind::PlayListAllEntriesMissing);
    }

    TEST(ScanErrorPolicy, everyKindHasItsOwnLabel)
    {
        for (std::size_t i{}; i < static_cast<std::size_t>(ScanErrorKind::Count); ++i)
        {
            const std::string_view label{ toString(static_cast<ScanErrorKind>(i)) };
            EXPECT_NE(label, "unknown");
            for (std::size_t j{}; j < i; ++j)
                EXPECT_NE(label, toString(static_cast<ScanErrorKind>(j)));
        }
    }

    // What production's scoped scans reported as a bare "errors = 967".
    TEST(ScanErrorPolicy, breakdownListsKindsLargestFirst)
    {
        ScanErrorCounts counts{};
        counts[static_cast<std::size_t>(ScanErrorKind::PlayListEntryMissing)] = 330;
        counts[static_cast<std::size_t>(ScanErrorKind::PlayListAllEntriesMissing)] = 637;
        counts[static_cast<std::size_t>(ScanErrorKind::ImageFile)] = 2;

        EXPECT_EQ(formatErrorBreakdown(counts), "637 playlist-all-entries-missing, 330 playlist-entry-missing, 2 image-unreadable");
        EXPECT_EQ(countOf(counts, ScanErrorKind::AudioFile), 0U);
    }

    TEST(ScanErrorPolicy, breakdownIsEmptyWithoutErrors)
    {
        EXPECT_EQ(formatErrorBreakdown(ScanErrorCounts{}), "");
    }

    TEST(ScanErrorPolicy, libraryScanReportsPlayListErrors)
    {
        EXPECT_EQ(decidePlayListErrorReporting("/music/EPs/Scantraxx/SCAN001/00-scan001.m3u", ScanOptions{}), PlayListErrorDecision::Report);
    }

    TEST(ScanErrorPolicy, scopedScanReportsPlayListErrorsInsideItsScope)
    {
        EXPECT_EQ(decidePlayListErrorReporting("/music/EPs/Scantraxx/SCAN001/00-scan001.m3u", scopedTo({ "/music/Youtube/X", "/music/EPs/Scantraxx/SCAN001" })),
                  PlayListErrorDecision::Report);
    }

    // The association step walks every playlist in the library; a scoped scan that read two
    // files used to count every stale playlist anywhere, on every run.
    TEST(ScanErrorPolicy, scopedScanSkipsPlayListErrorsOutsideItsScope)
    {
        EXPECT_EQ(decidePlayListErrorReporting("/music/Livesets/Defqon.1/2020/set/00-set.m3u", scopedTo({ "/music/EPs/Scantraxx/SCAN001" })),
                  PlayListErrorDecision::SkipOutOfScope);
    }

    TEST(ScanErrorPolicy, scopeMatchesWholeFolderNamesOnly)
    {
        EXPECT_EQ(decidePlayListErrorReporting("/music/EPs/Scantraxx Silver/SSL050/00-ssl050.m3u", scopedTo({ "/music/EPs/Scantraxx" })),
                  PlayListErrorDecision::SkipOutOfScope);
    }

    TEST(ScanErrorPolicy, importQueuePlayListsAreNeverReported)
    {
        const char* queued{ "/music/EPs/__TODO/Albino_-_HOLD_THE_BEAT_BACK-(U13016)-SINGLE-WEB-2026-SRG/00-albino.m3u" };
        EXPECT_EQ(decidePlayListErrorReporting(queued, ScanOptions{}), PlayListErrorDecision::SkipImportQueue);
        EXPECT_EQ(decidePlayListErrorReporting(queued, scopedTo({ "/music/EPs/__TODO/Albino_-_HOLD_THE_BEAT_BACK-(U13016)-SINGLE-WEB-2026-SRG" })),
                  PlayListErrorDecision::SkipImportQueue);
    }

    TEST(ScanErrorPolicy, importQueueMatchesTheWholeFolderName)
    {
        EXPECT_EQ(decidePlayListErrorReporting("/music/EPs/__TODO_old/release/00.m3u", ScanOptions{}), PlayListErrorDecision::Report);
    }

    TEST(ScanErrorPolicy, aVanishedFileIsNotAnError)
    {
        EXPECT_TRUE(isMissingFileError(std::make_error_code(std::errc::no_such_file_or_directory)));
        EXPECT_TRUE(isMissingFileError(std::make_error_code(std::errc::not_a_directory)));
    }

    TEST(ScanErrorPolicy, otherFileSystemFailuresStayErrors)
    {
        EXPECT_FALSE(isMissingFileError(std::make_error_code(std::errc::permission_denied)));
        EXPECT_FALSE(isMissingFileError(std::make_error_code(std::errc::io_error)));
    }
} // namespace lms::scanner::tests
