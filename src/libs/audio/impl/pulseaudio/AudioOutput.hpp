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

#include "audio/IAudioOutput.hpp"

extern "C"
{
    struct pa_context;
    struct pa_threaded_mainloop;
}

namespace lms::audio::pulseaudio
{
    struct PaContextDeleter
    {
        void operator()(pa_context* ctx) const noexcept;
    };
    using PaContextPtr = std::unique_ptr<pa_context, PaContextDeleter>;

    struct PaThreadedMainLoopDeleter
    {
        void operator()(pa_threaded_mainloop* mainloop) const noexcept;
    };
    using PaThreadedMainLoopPtr = std::unique_ptr<pa_threaded_mainloop, PaThreadedMainLoopDeleter>;

    class AudioOutputContext : public IAudioOutputContext
    {
    public:
        AudioOutputContext(boost::asio::io_context& ioContext, std::string_view name);
        ~AudioOutputContext() override;

        AudioOutputContext(const AudioOutputContext&) = delete;
        AudioOutputContext& operator=(const AudioOutputContext&) = delete;

    private:
        void asyncWaitReady(WaitReadyCallback cb) override;
        std::unique_ptr<IAudioOutputStream> createOutputStream(std::string_view name, const PcmParameters& outputParameters) override;

        void onStateChanged();

        boost::asio::io_context& _ioContext;
        std::vector<WaitReadyCallback> _waitReadyCallbacks;
        PaThreadedMainLoopPtr _mainLoop;
        PaContextPtr _context;
    };
} // namespace lms::audio::pulseaudio