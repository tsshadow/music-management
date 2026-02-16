/*
 * Copyright (C) 2025 Emeric Poupon
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
#include <functional>
#include <memory>
#include <string_view>

#include <boost/asio/io_context.hpp>

#include "core/EnumSet.hpp"

#include "audio/PcmTypes.hpp"

namespace lms::audio
{
    class IAudioOutputStream
    {
    public:
        virtual ~IAudioOutputStream() = default;

        virtual const PcmParameters& getParameters() const = 0;

        using WaitReadyCallback = std::function<void()>;
        virtual void asyncWaitReady(WaitReadyCallback cb) = 0;

        using WriteCompletionCallback = std::function<void()>;
        // Do not touch the buffer until cb is called
        virtual void asyncWrite(std::span<const std::byte> buffer, WriteCompletionCallback cb) = 0;

        using DrainCompletionCallback = std::function<void()>;
        virtual void asyncDrain(DrainCompletionCallback cb) = 0; // can be called only once, no other write can be done after

        // Get playback time since first resume
        virtual std::chrono::microseconds getPlaybackTime() const = 0;

        virtual std::chrono::microseconds getLatency() const = 0;

        // Discard all buffered writes (write callbacks will be called asap)
        virtual void flush() = 0;

        virtual void pause() = 0;
        virtual void resume() = 0;
        virtual bool isPaused() const = 0;
    };

    class IAudioOutputContext
    {
    public:
        virtual ~IAudioOutputContext() = default;

        using WaitReadyCallback = std::function<void()>;
        virtual void asyncWaitReady(WaitReadyCallback cb) = 0;

        // Must be called once output context is ready
        // The created stream is in pause state; you must call resume() to start it
        // Planar format is not accepted!
        [[nodiscard]] virtual std::unique_ptr<IAudioOutputStream> createOutputStream(std::string_view name, const PcmParameters& pcmParameters) = 0;
    };

    enum class AudioOutputBackend
    {
        Auto,
        ALSA,
        PulseAudio,
    };
    std::unique_ptr<IAudioOutputContext> createAudioOutputContext(boost::asio::io_context& ioContext, std::string_view name, AudioOutputBackend backend);
} // namespace lms::audio