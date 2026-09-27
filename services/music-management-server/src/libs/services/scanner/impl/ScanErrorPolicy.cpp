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

#include "ScanErrorPolicy.hpp"

#include <algorithm>
#include <cassert>
#include <utility>
#include <vector>

#include "core/Path.hpp"

namespace lms::scanner
{
    namespace
    {
        class ScanErrorKindVisitor : public ScanErrorVisitor
        {
        public:
            ScanErrorKind kind{ ScanErrorKind::IO };

            void visit([[maybe_unused]] const ScanError& error) override
            {
                // There should never be a ScanError without a specific type
                assert(false);
            }
            void visit(const IOScanError& /*error*/) override { kind = ScanErrorKind::IO; }
            void visit(const AudioFileScanError& /*error*/) override { kind = ScanErrorKind::AudioFile; }
            void visit(const EmbeddedImageScanError& /*error*/) override { kind = ScanErrorKind::EmbeddedImage; }
            void visit(const NoAudioTrackFoundError& /*error*/) override { kind = ScanErrorKind::NoAudioTrack; }
            void visit(const BadAudioDurationError& /*error*/) override { kind = ScanErrorKind::BadAudioDuration; }
            void visit(const ArtistInfoFileScanError& /*error*/) override { kind = ScanErrorKind::ArtistInfoFile; }
            void visit(const MissingArtistNameError& /*error*/) override { kind = ScanErrorKind::MissingArtistName; }
            void visit(const ImageFileScanError& /*error*/) override { kind = ScanErrorKind::ImageFile; }
            void visit(const LyricsFileScanError& /*error*/) override { kind = ScanErrorKind::LyricsFile; }
            void visit(const PlayListFileScanError& /*error*/) override { kind = ScanErrorKind::PlayListFile; }
            void visit(const PlayListFilePathMissingError& /*error*/) override { kind = ScanErrorKind::PlayListEntryMissing; }
            void visit(const PlayListFileAllPathesMissingError& /*error*/) override { kind = ScanErrorKind::PlayListAllEntriesMissing; }
        };

        bool isInImportQueue(const std::filesystem::path& path)
        {
            return std::any_of(std::cbegin(path), std::cend(path), [](const std::filesystem::path& component) { return component == importQueueDirName; });
        }
    } // namespace

    ScanErrorKind getScanErrorKind(const ScanError& error)
    {
        ScanErrorKindVisitor visitor;
        error.accept(visitor);
        return visitor.kind;
    }

    std::string_view toString(ScanErrorKind kind)
    {
        switch (kind)
        {
        case ScanErrorKind::IO:
            return "io";
        case ScanErrorKind::AudioFile:
            return "audio-unreadable";
        case ScanErrorKind::EmbeddedImage:
            return "embedded-image";
        case ScanErrorKind::NoAudioTrack:
            return "no-audio-track";
        case ScanErrorKind::BadAudioDuration:
            return "zero-duration";
        case ScanErrorKind::ArtistInfoFile:
            return "artist-info";
        case ScanErrorKind::MissingArtistName:
            return "artist-info-no-name";
        case ScanErrorKind::ImageFile:
            return "image-unreadable";
        case ScanErrorKind::LyricsFile:
            return "lyrics";
        case ScanErrorKind::PlayListFile:
            return "playlist";
        case ScanErrorKind::PlayListEntryMissing:
            return "playlist-entry-missing";
        case ScanErrorKind::PlayListAllEntriesMissing:
            return "playlist-all-entries-missing";
        case ScanErrorKind::Count:
            break;
        }
        return "unknown";
    }

    std::string formatErrorBreakdown(const ScanErrorCounts& counts)
    {
        std::vector<std::pair<std::size_t, ScanErrorKind>> nonZero;
        for (std::size_t i{}; i < counts.size(); ++i)
        {
            if (counts.at(i) > 0)
                nonZero.emplace_back(counts.at(i), static_cast<ScanErrorKind>(i));
        }
        // Largest first; equal counts keep the enum order so the line is deterministic.
        std::stable_sort(std::begin(nonZero), std::end(nonZero), [](const auto& lhs, const auto& rhs) { return lhs.first > rhs.first; });

        std::string res;
        for (const auto& [count, kind] : nonZero)
        {
            if (!res.empty())
                res += ", ";
            res += std::to_string(count);
            res += ' ';
            res += toString(kind);
        }
        return res;
    }

    PlayListErrorDecision decidePlayListErrorReporting(const std::filesystem::path& playListFile, const ScanOptions& options)
    {
        if (isInImportQueue(playListFile))
            return PlayListErrorDecision::SkipImportQueue;

        if (options.isScoped()
            && std::none_of(std::cbegin(options.scanDirectories), std::cend(options.scanDirectories),
                            [&](const std::filesystem::path& scope) { return core::pathUtils::isPathInRootPath(playListFile, scope); }))
        {
            return PlayListErrorDecision::SkipOutOfScope;
        }

        return PlayListErrorDecision::Report;
    }

    bool isMissingFileError(std::error_code ec)
    {
        return ec == std::errc::no_such_file_or_directory || ec == std::errc::not_a_directory;
    }
} // namespace lms::scanner
