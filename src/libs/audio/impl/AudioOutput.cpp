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

#include "audio/IAudioOutput.hpp"
#if LMS_HAVE_PULSEAUDIO
    #include "pulseaudio/AudioOutput.hpp"
#endif

#if LMS_HAVE_ALSA
    #include "alsa/AudioOutput.hpp"
#endif

namespace lms::audio
{
    std::unique_ptr<IAudioOutputContext> createAudioOutputContext([[maybe_unused]] boost::asio::io_context& ioContext, [[maybe_unused]] std::string_view name, AudioOutputBackend backend)
    {
        std::unique_ptr<IAudioOutputContext> context;

        switch (backend)
        {
        case AudioOutputBackend::Auto:
#if LMS_HAVE_PULSEAUDIO
            context = std::make_unique<pulseaudio::AudioOutputContext>(ioContext, name);
#endif
            break;

        case AudioOutputBackend::ALSA:
#if LMS_HAVE_ALSA
            context = std::make_unique<alsa::AudioOutputContext>(ioContext, name);
#endif
            break;

        case AudioOutputBackend::PulseAudio:
#if LMS_HAVE_PULSEAUDIO
            context = std::make_unique<pulseaudio::AudioOutputContext>(ioContext, name);
#endif
            break;
        }

        return context;
    }
} // namespace lms::audio