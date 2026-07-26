/*
 * Copyright (C) 2024 Emeric Poupon
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

#include "ArtistType.hpp"
#include "DropDownMenuSelector.hpp"

namespace lms::ui
{
    class ArtistTypeSelector : public DropDownMenuSelector<ArtistType>
    {
    public:
        ArtistTypeSelector(ArtistType defaultArtistType)
            : DropDownMenuSelector{ Wt::WString::tr("Lms.Explore.Artists.template.artist-type-selector"), defaultArtistType }
        {
            bindItem("artist-type-all", Wt::WString::tr("Lms.Explore.all-artists"), AllArtistsTag{});
            bindItem("artist-type-release-artist", Wt::WString::trn("Lms.Explore.release-artist", 2), ReleaseArtistsTag{});
            bindItem("artist-type-track-artist", Wt::WString::trn("Lms.Explore.track-artist", 2), db::TrackArtistLinkType::Artist);
            bindItem("artist-type-composer", Wt::WString::trn("Lms.Explore.composer", 2), db::TrackArtistLinkType::Composer);
            bindItem("artist-type-conductor", Wt::WString::trn("Lms.Explore.conductor", 2), db::TrackArtistLinkType::Conductor);
            bindItem("artist-type-lyricist", Wt::WString::trn("Lms.Explore.lyricist", 2), db::TrackArtistLinkType::Lyricist);
            bindItem("artist-type-mixer", Wt::WString::trn("Lms.Explore.mixer", 2), db::TrackArtistLinkType::Mixer);
            bindItem("artist-type-performer", Wt::WString::trn("Lms.Explore.performer", 2), db::TrackArtistLinkType::Performer);
            bindItem("artist-type-producer", Wt::WString::trn("Lms.Explore.producer", 2), db::TrackArtistLinkType::Producer);
            bindItem("artist-type-remixer", Wt::WString::trn("Lms.Explore.remixer", 2), db::TrackArtistLinkType::Remixer);
        }
    };
} // namespace lms::ui
