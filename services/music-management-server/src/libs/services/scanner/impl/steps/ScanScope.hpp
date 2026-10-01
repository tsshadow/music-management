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
#include <filesystem>
#include <optional>
#include <span>
#include <vector>

#include "database/IdRange.hpp"
#include "database/objects/ArtistId.hpp"
#include "database/objects/ClusterId.hpp"
#include "database/objects/MediumId.hpp"
#include "database/objects/PlayListFile.hpp" // PlayListFileId
#include "database/objects/ReleaseId.hpp"
#include "database/objects/TrackId.hpp"

namespace lms::db
{
    class Session;
}

namespace lms::scanner
{
    // What a scoped scan's association steps have to look at (bug report 141).
    //
    // Upstream LMS recomputes every release, artist, medium and track artwork, every playlist
    // and every cluster count after any scan with a change. That is right for a library-wide
    // scan and wrong for a scan of one folder: on production a scoped scan that read one file
    // spent 42 s doing it -- 18 s on the track artwork of 343,000 tracks alone -- and MuMa asks
    // for about 45 of them an hour, so LMS was scanning most of the time and every API read
    // competed with it.
    //
    // The scope is everything whose derived data can change because of what is under the scanned
    // folders:
    //   - tracks: every track under a scanned folder, plus every other track of their releases
    //     (a track falls back on its release's artwork, and a release may span folders);
    //   - releases and mediums of those tracks;
    //   - artists linked to those tracks, whatever the link type (release artists included);
    //   - clusters of those tracks;
    //   - playlist files under a scanned folder.
    //
    // What it leaves to the next library-wide scan: an entity outside the folders whose artwork
    // was an image the scan removed (the foreign key already set it to NULL, so it shows no
    // artwork rather than a broken one), a release elsewhere that would pick up an image named
    // after its MBID in a scanned folder, and a playlist elsewhere that lists a file of a scanned
    // folder. Cluster counts are not left behind: ScanStepComputeClusterStats adds every cluster
    // whose cached count no longer matches its rows.
    struct ScanScope
    {
        // Each sorted and without duplicates.
        std::vector<db::TrackId> tracks;
        std::vector<db::ReleaseId> releases;
        std::vector<db::MediumId> mediums;
        std::vector<db::ArtistId> artists;
        std::vector<db::ClusterId> clusters;
        std::vector<db::PlayListFileId> playListFiles;
    };

    // Above this many tracks a scoped scan is a library scan in all but name (a whole label
    // folder, say), and the per-track lookups below would cost more than they save.
    inline constexpr std::size_t maxScopedTrackCount{ 20'000 };

    // The scope of a scan over `directories`, read in one read transaction of its own, or
    // nothing when more than `maxTrackCount` tracks are involved -- the caller then does the
    // library-wide pass. Must run after the walk and the removal check, so that it sees the
    // tracks the scan added and not the ones it removed.
    std::optional<ScanScope> computeScanScope(db::Session& session, std::span<const std::filesystem::path> directories, std::size_t maxTrackCount = maxScopedTrackCount);

    // Splits sorted, unique ids into ranges of consecutive ids, at most `maxRangeSize` each, for
    // the association jobs, which read `BETWEEN first AND last`. A range never spans an id that
    // is not in `ids`, so a step processes exactly the scope and nothing next to it.
    template<typename IdType>
    std::vector<db::IdRange<IdType>> toConsecutiveIdRanges(std::span<const IdType> ids, std::size_t maxRangeSize = 100)
    {
        std::vector<db::IdRange<IdType>> ranges;

        std::size_t rangeSize{};
        for (const IdType id : ids)
        {
            if (!ranges.empty() && rangeSize < maxRangeSize && id.getValue() == ranges.back().last.getValue() + 1)
            {
                ranges.back().last = id;
                ++rangeSize;
                continue;
            }

            ranges.push_back(db::IdRange<IdType>{ .first = id, .last = id });
            rangeSize = 1;
        }

        return ranges;
    }
} // namespace lms::scanner
