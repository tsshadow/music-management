/*
 * Copyright (C) 2026 Emeric Poupon
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

#include "TrackArtistTypeSelector.hpp"

#include <array>

namespace lms::ui
{
    TrackArtistTypeSelector::TrackArtistTypeSelector(std::optional<db::TrackArtistLinkType> defaultRole, core::EnumSet<db::TrackArtistLinkType> types)
        : DropDownMenuSelector{ Wt::WString::tr("Lms.Explore.Artist.template.track-artist-type-selector"), defaultRole }
    {
        struct Entry
        {
            std::string var;
            Wt::WString title;
            std::optional<db::TrackArtistLinkType> linkType;
            core::LiteralString condition;
        };

        auto bindItemWithCondition = [&](const std::string& var, const Wt::WString& title, std::optional<db::TrackArtistLinkType> item, core::LiteralString condition) {
            if (!condition.empty())
                setCondition(condition.c_str(), true);
            bindItem(var, title, item);
        };
        const std::array entries{
            Entry{ "artist-type-all", Wt::WString::tr("Lms.Explore.all-roles"), std::nullopt, core::LiteralString{} },
            Entry{ "artist-type-track-artist", Wt::WString::trn("Lms.Explore.track-artist", 1), db::TrackArtistLinkType::Artist, "if-has-track-artist" },
            Entry{ "artist-type-composer", Wt::WString::trn("Lms.Explore.composer", 1), db::TrackArtistLinkType::Composer, "if-has-composer" },
            Entry{ "artist-type-conductor", Wt::WString::trn("Lms.Explore.conductor", 1), db::TrackArtistLinkType::Conductor, "if-has-conductor" },
            Entry{ "artist-type-lyricist", Wt::WString::trn("Lms.Explore.lyricist", 1), db::TrackArtistLinkType::Lyricist, "if-has-lyricist" },
            Entry{ "artist-type-mixer", Wt::WString::trn("Lms.Explore.mixer", 1), db::TrackArtistLinkType::Mixer, "if-has-mixer" },
            Entry{ "artist-type-performer", Wt::WString::trn("Lms.Explore.performer", 1), db::TrackArtistLinkType::Performer, "if-has-performer" },
            Entry{ "artist-type-producer", Wt::WString::trn("Lms.Explore.producer", 1), db::TrackArtistLinkType::Producer, "if-has-producer" },
            Entry{ "artist-type-remixer", Wt::WString::trn("Lms.Explore.remixer", 1), db::TrackArtistLinkType::Remixer, "if-has-remixer" },
        };

        for (const Entry& entry : entries)
        {
            if (!entry.linkType || types.contains(*entry.linkType))
                bindItemWithCondition(entry.var, entry.title, entry.linkType, entry.condition);
        }
    }
} // namespace lms::ui
