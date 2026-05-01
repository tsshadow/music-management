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

#include "AudioOutput.hpp"

#include <boost/asio/post.hpp>

#include "AudioOutputStream.hpp"

namespace lms::audio::alsa
{
    AudioOutputContext::AudioOutputContext(boost::asio::io_context& ioContext, std::string_view name)
        : _ioContext{ ioContext }
        , _name{ name }
        , _device{ "default" }
    {
    }

    AudioOutputContext::~AudioOutputContext() = default;

    void AudioOutputContext::asyncWaitReady(WaitReadyCallback cb)
    {
        // ALSA device is to be open when creating the stream, nothing to wait for here
        boost::asio::post(_ioContext, std::move(cb));
    }

    std::unique_ptr<IAudioOutputStream> AudioOutputContext::createOutputStream(std::string_view name, const PcmParameters& outputParameters)
    {
        return std::make_unique<AudioOutputStream>(_ioContext, _device, name, outputParameters);
    }
} // namespace lms::audio::alsa