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

#pragma once

#include <chrono>
#include <memory>
#include <span>
#include <vector>

#include "audio/IAudioOutput.hpp"
#include "database/objects/TrackId.hpp"

namespace lms
{
    namespace db
    {
        class IDb;
    }
} // namespace lms

namespace lms::jukebox
{
    class IJukeboxService
    {
    public:
        virtual ~IJukeboxService() = default;

        virtual void play(std::size_t trackIndex, std::chrono::microseconds offset) = 0;

        virtual void pause() = 0;
        virtual void resume() = 0;
        virtual bool isPaused() const = 0;

        virtual std::optional<std::size_t> getCurrentTrackIndex() const = 0; // may be unset if queue is cleared while playing
        virtual std::chrono::microseconds getPlaybackTrackTime() const = 0;

        // Play queue control
        virtual void clearTracks() = 0;
        virtual void removeTrack(std::size_t index) = 0;
        virtual void appendTracks(std::span<const db::TrackId> tracks) = 0;
        virtual void shuffleTracks() = 0;
        virtual std::vector<db::TrackId> getTracks() const = 0;
    };

    std::unique_ptr<IJukeboxService> createJukeboxService(db::IDb& db, audio::AudioOutputBackend backend);
} // namespace lms::jukebox
