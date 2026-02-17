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

#include "JukeboxService.hpp"

#include <chrono>
#include <cstdlib>
#include <format>
#include <thread>

#include <boost/asio/io_context.hpp>
#include <boost/asio/post.hpp>

#include "core/ILogger.hpp"
#include "core/Random.hpp"

#include "audio/Exception.hpp"
#include "audio/IAudioOutput.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Track.hpp"

namespace lms::jukebox
{

    std::unique_ptr<IJukeboxService> createJukeboxService(db::IDb& db, audio::AudioOutputBackend backend)
    {
        return std::make_unique<JukeboxService>(db, backend);
    }

    JukeboxService::JukeboxService(db::IDb& db, audio::AudioOutputBackend backend)
        : _ioContextRunner{ _ioContext, 1, "Jukebox" }
        , _db{ db }
        , _outputContext{ audio::createAudioOutputContext(_ioContext, "LMS-Jukebox", backend) }
    {
        LMS_LOG(JUKEBOX, INFO, "Starting service...");

        // TODO create a context and an output stream only if a song is actually played
        _outputContext->asyncWaitReady([this] { onContextReady(); });
    }

    JukeboxService::~JukeboxService()
    {
        LMS_LOG(JUKEBOX, INFO, "Stopping service...");
        if (_decoder)
            _decoder->abort();

        _ioContextRunner.wait();
        LMS_LOG(JUKEBOX, INFO, "Service stopped!");
    }

    void JukeboxService::play(std::size_t trackIndex, std::chrono::microseconds offset)
    {
        LMS_LOG(JUKEBOX, INFO, "Playing track index " << trackIndex << " at offset " << std::format("{:%T}", offset));

        std::unique_lock lock{ _mutex };

        if (trackIndex >= _tracks.size())
        {
            LMS_LOG(JUKEBOX, INFO, "Requested track index out of bound: stopping");
            _currentTrackIndex.reset();
            return;
        }

        if (!_outputStream)
            return;

        abortDecoder();
        if (startDecoder(trackIndex, offset))
        {
            _currentTrackIndex = trackIndex;
            _currentTrackPlaybackTimeOffset = _outputStream->getPlaybackTime();
            _currentTrackStartTimeOffset = offset;
            _outputStream->resume();
        }
        // TODO if failure, switch to the next song?
    }

    void JukeboxService::pause()
    {
        std::unique_lock lock{ _mutex };

        if (_outputStream)
            _outputStream->pause();
    }

    void JukeboxService::resume()
    {
        std::unique_lock lock{ _mutex };

        if (_outputStream)
            _outputStream->resume();
    }

    bool JukeboxService::isPaused() const
    {
        std::shared_lock lock{ _mutex };

        if (!_outputStream)
            return true;

        return _outputStream->isPaused();
    }

    void JukeboxService::setVolume(float volume)
    {
        std::unique_lock lock{ _mutex };

        _outputStream->setVolume(volume);
    }

    float JukeboxService::getVolume() const
    {
        std::shared_lock lock{ _mutex };

        return _outputStream->getVolume();
    }

    std::optional<std::size_t> JukeboxService::getCurrentTrackIndex() const
    {
        std::shared_lock lock{ _mutex };

        return _currentTrackIndex;
    }

    std::chrono::microseconds JukeboxService::getPlaybackTrackTime() const
    {
        std::shared_lock lock{ _mutex };

        if (!_outputStream)
            return {};

        const auto playbackTime{ _outputStream->getPlaybackTime() };

        // If negative, this means we are still playing the buffered previous song, just report 0 as:
        // - the time window should be short enough to be ok-ish for the usage
        // - we would need to save back the previous track info (index, duration, start offset, etc.) and report accordingly in getCurrentTrackIndex
        if (playbackTime < _currentTrackPlaybackTimeOffset)
            return {};

        return playbackTime - _currentTrackPlaybackTimeOffset + _currentTrackStartTimeOffset;
    }

    void JukeboxService::clearTracks()
    {
        std::unique_lock lock{ _mutex };

        _tracks.clear();
        _currentTrackIndex.reset();
    }

    void JukeboxService::removeTrack(std::size_t index)
    {
        std::unique_lock lock{ _mutex };

        if (index >= _tracks.size())
            return;

        if (_currentTrackIndex)
        {
            if (*_currentTrackIndex == index)
                _currentTrackIndex.reset();
            else if (*_currentTrackIndex > index)
                (*_currentTrackIndex)--;
        }

        _tracks.erase(std::next(_tracks.begin(), index));
    }

    void JukeboxService::appendTracks(std::span<const db::TrackId> tracks)
    {
        LMS_LOG(JUKEBOX, INFO, "Appending " << tracks.size() << " tracks");

        std::unique_lock lock{ _mutex };

        _tracks.insert(std::end(_tracks), std::cbegin(tracks), std::cend(tracks));
    }

    void JukeboxService::shuffleTracks()
    {
        std::unique_lock lock{ _mutex };

        core::random::shuffleContainer(_tracks);

        // can't really determine the new pos if the song has been enqueued several times
        _currentTrackIndex.reset();
    }

    std::vector<db::TrackId> JukeboxService::getTracks() const
    {
        std::shared_lock lock{ _mutex };

        return _tracks;
    }

    void JukeboxService::onContextReady()
    {
        _outputStream = _outputContext->createOutputStream("LMS-jukebox", _pcmParams);
        _outputStream->asyncWaitReady([this] { onStreamReady(); });
    }

    void JukeboxService::onStreamReady()
    {
        audio::utils::PcmDecodeStreamerParameters params{
            .outputStream = *_outputStream,
            .bufferCount = 3,
            .bufferDuration = std::chrono::milliseconds{ 100 },
        };

        _decoder = audio::utils::createPcmDecodeStreamer(_ioContext, params);
    }

    bool JukeboxService::startDecoder(std::size_t trackIndex, std::chrono::microseconds offset)
    {
        if (!_decoder)
            return false;

        std::filesystem::path trackPath;
        {
            auto& session{ _db.getTLSSession() };
            auto transaction{ session.createReadTransaction() };

            const db::Track::pointer track{ db::Track::find(session, _tracks.at(trackIndex)) };
            if (!track)
            {
                LMS_LOG(JUKEBOX, DEBUG, "Track ID " << _tracks.at(trackIndex).getValue() << " not found");
                return false;
            }

            trackPath = track->getAbsoluteFilePath();
        }

        try
        {
            _decoder->start(trackPath, offset, [this](bool aborted) {
                onDecodeFinished(aborted);
            });
        }
        catch (const audio::Exception& e)
        {
            LMS_LOG(JUKEBOX, ERROR, "Failed to start PCM decoder for track " << trackPath);
            return false;
        }

        return true;
    }

    void JukeboxService::abortDecoder()
    {
        // Must not be called from within owned io_context
        if (_decoder)
        {
            _decoder->abort();

            // Should be hopefully short since flushing/aborting
            while (!_decoder->isComplete())
                std::this_thread::yield(); // TODO: execute some io_context stuff?
        }
    }

    void JukeboxService::onDecodeFinished(bool aborted)
    {
        if (aborted)
            return; // already setup to play next song, if needed

        std::unique_lock lock{ _mutex };

        _currentTrackPlaybackTimeOffset = {};
        _currentTrackStartTimeOffset = {};

        if (!_currentTrackIndex)
        {
            _outputStream->pause();
            return;
        }

        if (++(*_currentTrackIndex) >= _tracks.size())
        {
            _currentTrackIndex.reset();
            // let the output stream run out of data
            return;
        }

        if (startDecoder(*_currentTrackIndex))
        {
            _currentTrackPlaybackTimeOffset = _outputStream->getPlaybackTime() + _outputStream->getLatency();
            _currentTrackStartTimeOffset = {};
        }
        else
        {
            _currentTrackIndex.reset();
        }
        // TODO if failure, switch to the next song?
    }
} // namespace lms::jukebox