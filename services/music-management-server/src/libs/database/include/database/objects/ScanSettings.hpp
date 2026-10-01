/*
 * Copyright (C) 2018 Emeric Poupon
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

#include <span>
#include <string>
#include <string_view>
#include <vector>

#include <Wt/Dbo/Field.h>
#include <Wt/WTime.h>

#include "database/IdType.hpp"
#include "database/Object.hpp"

LMS_DECLARE_IDTYPE(ScanSettingsId)

namespace lms::db
{
    class Session;

    class ScanSettings final : public Object<ScanSettings, ScanSettingsId>
    {
    public:
        // Do not modify values (just add)
        enum class UpdatePeriod
        {
            Never = 0,
            Daily,
            Weekly,
            Monthly,
            Hourly,
        };

        // Do not modify values (just add)
        enum class FullScanPeriod
        {
            Never = 0,
            Weekly,
        };

        // Do not modify values (just add)
        enum class SimilarityEngineType
        {
            Clusters = 0,
            Features,
            None,
        };

        ScanSettings() = default;

        static pointer find(Session& session, std::string_view name = "");
        static pointer find(Session& session, ScanSettingsId id);

        // Getters
        std::size_t getAudioScanVersion() const { return _audioScanVersion; }
        std::size_t getArtistInfoScanVersion() const { return _artistInfoScanVersion; }
        Wt::WTime getUpdateStartTime() const { return _startTime; }
        UpdatePeriod getUpdatePeriod() const { return _updatePeriod; }
        FullScanPeriod getFullScanPeriod() const { return _fullScanPeriod; }
        int getFullScanDayOfWeek() const { return _fullScanDayOfWeek; }
        std::vector<std::string_view> getExtraTagsToScan() const;
        SimilarityEngineType getSimilarityEngineType() const { return _similarityEngineType; }
        std::vector<std::string> getArtistTagDelimiters() const;
        std::vector<std::string> getDefaultTagDelimiters() const;
        std::vector<std::string> getArtistsToNotSplit() const;
        bool getSkipSingleReleasePlayLists() const { return _skipSingleReleasePlayLists; }
        bool getAllowMBIDArtistMerge() const { return _allowMBIDArtistMerge; }
        bool getArtistImageFallbackToReleaseField() const { return _artistImageFallbackToReleaseField; }
        // Fingerprint of the release artwork rules the last scan applied (bug report 144). Only
        // the `last_scan` row carries one; the current rules come from lms.conf.
        std::string_view getReleaseArtworkRules() const { return _releaseArtworkRules; }

        // Setters
        void setUpdateStartTime(Wt::WTime t) { _startTime = t; }
        void setUpdatePeriod(UpdatePeriod p) { _updatePeriod = p; }
        void setFullScanPeriod(FullScanPeriod p) { _fullScanPeriod = p; }
        void setFullScanDayOfWeek(int dayOfWeek) { _fullScanDayOfWeek = dayOfWeek; }
        void setExtraTagsToScan(std::span<const std::string_view> extraTags);
        void setSimilarityEngineType(SimilarityEngineType type) { _similarityEngineType = type; }
        void setArtistTagDelimiters(std::span<const std::string_view> delimiters);
        void setArtistsToNotSplit(std::span<const std::string_view> artists);
        void setDefaultTagDelimiters(std::span<const std::string_view> delimiters);
        void setSkipSingleReleasePlayLists(bool value);
        void setAllowMBIDArtistMerge(bool value);
        void setArtistImageFallbackToReleaseField(bool value);
        void setReleaseArtworkRules(std::string_view value) { _releaseArtworkRules = value; }

        template<class Action>
        void persist(Action& a)
        {
            Wt::Dbo::field(a, _name, "name");
            Wt::Dbo::field(a, _audioScanVersion, "audio_scan_version");
            Wt::Dbo::field(a, _artistInfoScanVersion, "artist_info_scan_version");
            Wt::Dbo::field(a, _startTime, "start_time");
            Wt::Dbo::field(a, _updatePeriod, "update_period");
            Wt::Dbo::field(a, _fullScanPeriod, "full_scan_period");
            Wt::Dbo::field(a, _fullScanDayOfWeek, "full_scan_day_of_week");
            Wt::Dbo::field(a, _similarityEngineType, "similarity_engine_type");
            Wt::Dbo::field(a, _extraTagsToScan, "extra_tags_to_scan");
            Wt::Dbo::field(a, _artistTagDelimiters, "artist_tag_delimiters");
            Wt::Dbo::field(a, _artistsToNotSplit, "artists_to_not_split");
            Wt::Dbo::field(a, _defaultTagDelimiters, "default_tag_delimiters");
            Wt::Dbo::field(a, _skipSingleReleasePlayLists, "skip_single_release_playlists");
            Wt::Dbo::field(a, _allowMBIDArtistMerge, "allow_mbid_artist_merge");
            Wt::Dbo::field(a, _artistImageFallbackToReleaseField, "artist_image_fallback_to_release");
            Wt::Dbo::field(a, _releaseArtworkRules, "release_artwork_rules");
        }

    private:
        friend class Session;

        ScanSettings(std::string_view name);
        static pointer create(Session& session, std::string_view name = "");

        void incAudioScanVersion();

        std::string _name;
        int _audioScanVersion{};
        int _artistInfoScanVersion{};
        Wt::WTime _startTime = Wt::WTime{ 0, 0, 0 };
        UpdatePeriod _updatePeriod{ UpdatePeriod::Never };
        FullScanPeriod _fullScanPeriod{ FullScanPeriod::Never };
        int _fullScanDayOfWeek{ 7 }; // Sunday; Wt::WDate::dayOfWeek() is 1..7, Monday first
        SimilarityEngineType _similarityEngineType{ SimilarityEngineType::Clusters };
        std::string _extraTagsToScan;
        std::string _artistTagDelimiters;
        std::string _artistsToNotSplit;
        std::string _defaultTagDelimiters;
        bool _skipSingleReleasePlayLists{};
        bool _allowMBIDArtistMerge{};
        bool _artistImageFallbackToReleaseField{};
        std::string _releaseArtworkRules;
    };
} // namespace lms::db
