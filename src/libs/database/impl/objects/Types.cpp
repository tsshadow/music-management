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

#include "database/objects/Types.hpp"

#include <unordered_set>

namespace lms::db
{
    core::LiteralString trackArtistLinkTypeToString(TrackArtistLinkType type)
    {
        switch (type)
        {
        case TrackArtistLinkType::Arranger:
            return "arranger";
        case TrackArtistLinkType::Artist:
            return "artist";
        case TrackArtistLinkType::Composer:
            return "composer";
        case TrackArtistLinkType::Conductor:
            return "conductor";
        case TrackArtistLinkType::Lyricist:
            return "lyricist";
        case TrackArtistLinkType::Mixer:
            return "mixer";
        case TrackArtistLinkType::Performer:
            return "performer";
        case TrackArtistLinkType::Producer:
            return "producer";
        case TrackArtistLinkType::ReleaseArtist:
            return "albumartist";
        case TrackArtistLinkType::Remixer:
            return "remixer";
        case TrackArtistLinkType::Writer:
            return "writer";
        }

        return "unknown";
    }

    static const std::unordered_set<Bitrate> allowedAudioBitrates{
        64000,
        96000,
        128000,
        192000,
        320000,
    };

    void visitAllowedAudioBitrates(std::function<void(Bitrate)> func)
    {
        for (Bitrate bitrate : allowedAudioBitrates)
            func(bitrate);
    }

    bool isAudioBitrateAllowed(Bitrate bitrate)
    {
        return allowedAudioBitrates.find(bitrate) != std::cend(allowedAudioBitrates);
    }

    TrackSortMethod stringToSortMethod(const std::string& input)
    {
        if (input == "Id") return TrackSortMethod::Id;
        if (input == "None") return TrackSortMethod::None;
        if (input == "Random") return TrackSortMethod::Random;
        if (input == "AddedDesc") return TrackSortMethod::AddedDesc;
        if (input == "LastWrittenDesc") return TrackSortMethod::LastWrittenDesc;
        if (input == "StarredDateDesc") return TrackSortMethod::StarredDateDesc;
        if (input == "Name") return TrackSortMethod::Name;
        if (input == "DateDescAndRelease") return TrackSortMethod::DateDescAndRelease;
        if (input == "Release") return TrackSortMethod::Release;
        if (input == "TrackList") return TrackSortMethod::TrackList;
        if (input == "MostPlayed") return TrackSortMethod::MostPlayed;
        if (input == "RecentlyPlayed") return TrackSortMethod::RecentlyPlayed;
        if (input == "TrackNumber") return TrackSortMethod::TrackNumber;
        if (input == "AbsoluteFilePath") return TrackSortMethod::AbsoluteFilePath;

        return TrackSortMethod::Name; // fallback
    }

    std::string sortMethodToString(TrackSortMethod input)
    {
        switch (input)
        {
        case TrackSortMethod::Id:
            return "Id";
        case TrackSortMethod::None:
            return "None";
        case TrackSortMethod::Random:
            return "Random";
        case TrackSortMethod::AddedDesc:
            return "AddedDesc";
        case TrackSortMethod::LastWrittenDesc:
            return "LastWrittenDesc";
        case TrackSortMethod::StarredDateDesc:
            return "StarredDateDesc";
        case TrackSortMethod::Name:
            return "Name";
        case TrackSortMethod::DateDescAndRelease:
            return "DateDescAndRelease";
        case TrackSortMethod::Release:
            return "Release";
        case TrackSortMethod::TrackList:
            return "TrackList";
        case TrackSortMethod::MostPlayed:
            return "MostPlayed";
        case TrackSortMethod::RecentlyPlayed:
            return "RecentlyPlayed";
        case TrackSortMethod::TrackNumber:
            return "TrackNumber";
        case TrackSortMethod::AbsoluteFilePath:
            return "AbsoluteFilePath";
        default:
            return "Unknown";
        }
    }

    std::string sortMethodToSQL(TrackSortMethod input)
    {
        switch (input)
        {
        case TrackSortMethod::None:
            return "t.id";
        case TrackSortMethod::Id:
            return "t.id";
        case TrackSortMethod::Random:
            return "RANDOM()";
        case TrackSortMethod::LastWrittenDesc:
            return "t.file_last_write DESC";
        case TrackSortMethod::AddedDesc:
            return "t.file_added DESC";
        case TrackSortMethod::StarredDateDesc:
            return "t.starred_date DESC";
        case TrackSortMethod::AbsoluteFilePath:
            return "t.file_name";
        case TrackSortMethod::Name:
            return "t.name";
        case TrackSortMethod::DateDescAndRelease:
            return "t.date DESC, t.release_id, t.track_number";
        case TrackSortMethod::Release:
            return "t.track_number";
        case TrackSortMethod::TrackList:
            return "t.tracklist_order";
        case TrackSortMethod::TrackNumber:
            return "t.track_number";
        case TrackSortMethod::MostPlayed:
            return "t.play_count DESC, t.last_play DESC";
        case TrackSortMethod::RecentlyPlayed:
            return "t.last_play DESC";

        default:
            return "t.id";
        }
    }
} // namespace lms::db
