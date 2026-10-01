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

#include "ReleaseArtworkRules.hpp"

#include <algorithm>
#include <limits>
#include <string_view>

#include "core/IConfig.hpp"
#include "core/Service.hpp"

namespace lms::scanner
{
    namespace
    {
        // Bump when the way the rules are applied changes, so that the next scan recomputes the
        // artwork of every release even though lms.conf did not change.
        constexpr std::string_view releaseArtworkRulesCodeVersion{ "1" };

        constexpr std::size_t noRank{ std::numeric_limits<std::size_t>::max() };

        std::vector<std::string> readStrings(std::string_view setting, std::initializer_list<std::string_view> defaults)
        {
            std::vector<std::string> res;
            core::Service<core::IConfig>::get()->visitStrings(setting, [&res](std::string_view value) { res.emplace_back(value); }, defaults);
            return res;
        }

        bool isAsciiAlnum(char c)
        {
            return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
        }

        bool isAsciiDigit(char c)
        {
            return c >= '0' && c <= '9';
        }

        char toAsciiLower(char c)
        {
            return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
        }

        std::string toAsciiLower(std::string_view str)
        {
            std::string res{ str };
            std::ranges::transform(res, res.begin(), [](char c) { return toAsciiLower(c); });
            return res;
        }

        // The runs of ASCII letters and digits, lowercased: "00-Artist_-_Title-(CAT1)" ->
        // "00", "artist", "title", "cat1".
        std::vector<std::string> splitWords(std::string_view str)
        {
            std::vector<std::string> words;
            std::string current;
            for (const char c : str)
            {
                if (isAsciiAlnum(c))
                {
                    current += toAsciiLower(c);
                }
                else if (!current.empty())
                {
                    words.push_back(std::move(current));
                    current.clear();
                }
            }
            if (!current.empty())
            {
                words.push_back(std::move(current));
            }
            return words;
        }

        // "2004", "1999", but also scene's "199x".
        bool isYearWord(std::string_view word)
        {
            constexpr std::size_t yearLength{ 4 };
            if (word.size() != yearLength)
            {
                return false;
            }
            if (!word.starts_with("19") && !word.starts_with("20"))
            {
                return false;
            }
            return isAsciiDigit(word.at(2)) && (isAsciiDigit(word.at(3)) || word.at(3) == 'x');
        }

        // The words after the last year: what a lone scene image adds to its release's name.
        std::vector<std::string> wordsAfterLastYear(std::string_view stem)
        {
            std::vector<std::string> words{ splitWords(stem) };
            const auto lastYear{ std::find_if(words.rbegin(), words.rend(), [](const std::string& word) { return isYearWord(word); }) };
            if (lastYear == words.rend())
            {
                return {};
            }
            words.erase(words.begin(), lastYear.base());
            return words;
        }

        // Whether `pos` falls between two words in every string: at either end, or with a
        // character that is not a letter or digit on one side of it.
        bool isWordBoundary(std::span<const std::string> strs, std::size_t pos)
        {
            return std::ranges::all_of(strs, [pos](const std::string& str) {
                if (pos == 0 || pos >= str.size())
                {
                    return true;
                }
                return !isAsciiAlnum(str.at(pos - 1)) || !isAsciiAlnum(str.at(pos));
            });
        }

        // Length of the part all strings start with, cut back to a word boundary so that
        // "pro|of" and "pro|per" are told apart by their whole word.
        std::size_t commonPrefixLength(std::span<const std::string> strs)
        {
            std::size_t length{ strs.front().size() };
            for (const std::string& str : strs.subspan(1))
            {
                const auto mismatch{ std::ranges::mismatch(strs.front(), str) };
                length = std::min(length, static_cast<std::size_t>(mismatch.in1 - strs.front().begin()));
            }
            while (length > 0 && !isWordBoundary(strs, length))
            {
                --length;
            }
            return length;
        }

        // The distinguishing words of each of several stems: what is left once the start and
        // the end they all share are removed.
        std::vector<std::vector<std::string>> distinguishingWords(std::span<const std::string> stems)
        {
            std::vector<std::string> lowered;
            lowered.reserve(stems.size());
            for (const std::string& stem : stems)
            {
                lowered.push_back(toAsciiLower(stem));
            }

            std::vector<std::string> reversed;
            reversed.reserve(lowered.size());
            for (const std::string& str : lowered)
            {
                reversed.emplace_back(str.rbegin(), str.rend());
            }

            const std::size_t prefixLength{ commonPrefixLength(lowered) };
            const std::size_t suffixLength{ commonPrefixLength(reversed) };

            std::vector<std::vector<std::string>> res;
            res.reserve(lowered.size());
            for (const std::string& str : lowered)
            {
                if (prefixLength + suffixLength >= str.size())
                {
                    res.emplace_back();
                }
                else
                {
                    res.push_back(splitWords(std::string_view{ str }.substr(prefixLength, str.size() - prefixLength - suffixLength)));
                }
            }
            return res;
        }

        bool hasExcludedWord(const ReleaseArtworkRules& rules, std::span<const std::string> words)
        {
            return std::ranges::any_of(words, [&rules](const std::string& word) {
                std::string_view bare{ word };
                while (!bare.empty() && isAsciiDigit(bare.front()))
                {
                    bare.remove_prefix(1);
                }
                return std::ranges::any_of(rules.fallbackExcludedWords, [bare](const std::string& excluded) {
                    return !excluded.empty() && bare.starts_with(toAsciiLower(excluded));
                });
            });
        }

        // Position in fallbackFrontWords of the first front word found in `words`.
        std::size_t frontRank(const ReleaseArtworkRules& rules, std::span<const std::string> words)
        {
            for (std::size_t rank{}; rank < rules.fallbackFrontWords.size(); ++rank)
            {
                const std::string front{ toAsciiLower(rules.fallbackFrontWords.at(rank)) };
                if (front.empty())
                {
                    continue;
                }
                if (std::ranges::any_of(words, [&front](const std::string& word) { return word.find(front) != std::string::npos; }))
                {
                    return rank;
                }
            }
            return noRank;
        }

        bool hasFallbackPrefix(const ReleaseArtworkRules& rules, std::string_view stem)
        {
            const std::string lowered{ toAsciiLower(stem) };
            return std::ranges::any_of(rules.fallbackFileStemPrefixes, [&lowered](const std::string& prefix) {
                return lowered.starts_with(toAsciiLower(prefix));
            });
        }

        struct FallbackCandidate
        {
            std::size_t index; // in the stems given to pickFallbackReleaseImage
            std::string stem;
        };

        std::optional<std::size_t> pickByFileStemPrefix(const ReleaseArtworkRules& rules, std::span<const std::string> stems)
        {
            std::vector<FallbackCandidate> candidates;
            std::size_t index{};
            for (const std::string& stem : stems)
            {
                if (hasFallbackPrefix(rules, stem))
                {
                    candidates.push_back(FallbackCandidate{ .index = index, .stem = stem });
                }
                ++index;
            }
            if (candidates.empty())
            {
                return std::nullopt;
            }

            // The order the database returned them in is not a contract; the stem is.
            std::ranges::sort(candidates, [](const FallbackCandidate& lhs, const FallbackCandidate& rhs) { return toAsciiLower(lhs.stem) < toAsciiLower(rhs.stem); });

            std::vector<std::vector<std::string>> words;
            if (candidates.size() == 1)
            {
                words.push_back(wordsAfterLastYear(candidates.front().stem));
            }
            else
            {
                std::vector<std::string> candidateStems;
                candidateStems.reserve(candidates.size());
                for (const FallbackCandidate& candidate : candidates)
                {
                    candidateStems.push_back(candidate.stem);
                }
                words = distinguishingWords(candidateStems);
            }

            std::optional<std::size_t> best;
            std::size_t bestRank{ noRank };
            for (std::size_t i{}; i < candidates.size(); ++i)
            {
                if (hasExcludedWord(rules, words.at(i)))
                {
                    continue;
                }
                const std::size_t rank{ frontRank(rules, words.at(i)) };
                if (!best || rank < bestRank)
                {
                    best = candidates.at(i).index;
                    bestRank = rank;
                }
            }
            return best;
        }
    } // namespace

    ReleaseArtworkRules readReleaseArtworkRules()
    {
        ReleaseArtworkRules rules;
        rules.preferredFileNames = readStrings("cover-preferred-file-names", { "cover", "front", "folder", "default" });
        rules.fallbackFileStemPrefixes = readStrings("cover-fallback-file-stem-prefixes", { "00" });
        rules.fallbackFrontWords = readStrings("cover-fallback-front-words", { "front", "cover", "folder" });
        rules.fallbackExcludedWords = readStrings("cover-fallback-excluded-words", { "back", "proof", "poof", "inlay", "inside", "inner", "booklet", "cd", "disc", "disk", "scan", "tray", "matrix", "spine", "rear", "obi", "sticker", "log", "nfo", "total" });
        rules.singleImageFallback = core::Service<core::IConfig>::get()->getBool("cover-single-image-fallback", true);
        return rules;
    }

    std::string computeReleaseArtworkRulesFingerprint(const ReleaseArtworkRules& rules)
    {
        // '\x1f' (unit separator) cannot occur in a value of lms.conf.
        std::string res{ "v" };
        res += releaseArtworkRulesCodeVersion;
        const auto append{ [&res](std::string_view key, std::span<const std::string> values) {
            res += '\x1e';
            res += key;
            for (const std::string& value : values)
            {
                res += '\x1f';
                res += value;
            }
        } };
        append("names", rules.preferredFileNames);
        append("prefixes", rules.fallbackFileStemPrefixes);
        append("front", rules.fallbackFrontWords);
        append("excluded", rules.fallbackExcludedWords);
        res += '\x1e';
        res += rules.singleImageFallback ? "single" : "nosingle";
        return res;
    }

    std::optional<std::size_t> pickFallbackReleaseImage(const ReleaseArtworkRules& rules, std::span<const std::string> stems)
    {
        if (std::optional<std::size_t> picked{ pickByFileStemPrefix(rules, stems) })
        {
            return picked;
        }

        if (rules.singleImageFallback && stems.size() == 1 && !hasExcludedWord(rules, splitWords(stems.front())))
        {
            return 0;
        }

        return std::nullopt;
    }
} // namespace lms::scanner
