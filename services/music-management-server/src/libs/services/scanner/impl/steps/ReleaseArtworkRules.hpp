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
#include <span>
#include <string>
#include <vector>

namespace lms::scanner
{
    // What the release artwork search looks for in a release's directories (bug report 144).
    //
    // `preferredFileNames` is upstream's `cover-preferred-file-names`: tried first, in order,
    // wildcards allowed. When none of them matches, the fallback below picks among the images
    // of the directory by their file stem, because scene releases name their cover after the
    // release (`00-artist_-_title-(cat)-web-2026.jpg`) and ship proofs, back covers and disc
    // scans next to it under the same prefix.
    struct ReleaseArtworkRules
    {
        std::vector<std::string> preferredFileNames;       // cover-preferred-file-names
        std::vector<std::string> fallbackFileStemPrefixes; // cover-fallback-file-stem-prefixes, empty turns the stem rule off
        std::vector<std::string> fallbackFrontWords;       // cover-fallback-front-words, best first
        std::vector<std::string> fallbackExcludedWords;    // cover-fallback-excluded-words
        bool singleImageFallback{};                        // cover-single-image-fallback

        bool operator==(const ReleaseArtworkRules& rhs) const = default;
    };

    // The rules as lms.conf sets them; a key the file does not have takes the code default,
    // which conf/lms.conf repeats.
    ReleaseArtworkRules readReleaseArtworkRules();

    // A string that changes whenever the rules, or the code that applies them, change. Stored
    // with the last scan's settings: a scan that finds it different from the stored one
    // recomputes the artwork of every release, not only of what it read.
    std::string computeReleaseArtworkRulesFingerprint(const ReleaseArtworkRules& rules);

    // The fallback, for a directory none of the preferred names matched. `stems` holds the file
    // stems of every image in the directory; returns the index of the one to use, if any.
    //
    // 1. Candidates are the stems starting with one of the fallback prefixes (case-insensitive).
    // 2. Each candidate is judged on its distinguishing part only, so that a word of the title
    //    ("run_it_back") does not count: with several candidates, what is left once the part
    //    they all share at the start and at the end is removed ("front", "back", "proof"); with
    //    one, what follows its last year ("...-web-2014-srg-proof" -> "srg", "proof").
    // 3. A candidate whose distinguishing part has a word starting with an excluded word
    //    (digits in front ignored: "2back", "proof1", "cd1") is dropped.
    // 4. Of the rest, one with a front word in it wins (the earliest front word, then the stem);
    //    otherwise the first by stem.
    // 5. With no candidate left and exactly one image in the directory, that image -- unless one
    //    of its words starts with an excluded word.
    std::optional<std::size_t> pickFallbackReleaseImage(const ReleaseArtworkRules& rules, std::span<const std::string> stems);
} // namespace lms::scanner
