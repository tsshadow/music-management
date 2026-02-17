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

#include "audio/IAudioOutput.hpp"

#include <deque>
#include <thread>
#include <vector>

#include <alsa/asoundlib.h>
#include <boost/asio/posix/stream_descriptor.hpp>
#include <boost/asio/strand.hpp>

namespace lms::audio::alsa
{
    struct SndPcmDeleter
    {
        void operator()(snd_pcm_t* ctx) const noexcept;
    };
    using SndPcmPtr = std::unique_ptr<snd_pcm_t, SndPcmDeleter>;

    class AudioOutputStream : public IAudioOutputStream
    {
    public:
        AudioOutputStream(boost::asio::io_context& ioContext, std::string_view device, std::string_view name, const PcmParameters& outputParameters);
        ~AudioOutputStream() override;

        AudioOutputStream(AudioOutputStream&) = delete;
        AudioOutputStream& operator=(AudioOutputStream&) = delete;

    private:
        const PcmParameters& getParameters() const override;
        void asyncWaitReady(WaitReadyCallback cb) override;
        void asyncWrite(std::span<const std::byte> buffer, WriteCompletionCallback cb) override;
        void asyncDrain(DrainCompletionCallback cb) override;

        std::chrono::microseconds getPlaybackTime() const override;
        std::chrono::microseconds getLatency() const override;

        void flush() override;

        void pause() override;
        void resume() override;
        bool isPaused() const override;

        void setVolume(float volume) override;
        float getVolume() const override;

        void stop();
        void setupAllDescriptors();
        void releaseAllDescriptors();
        void asyncWaitAllDescriptors();
        void cancelAllDescriptors();
        void asyncWaitDescriptor(boost::asio::posix::stream_descriptor& streamDescriptor, boost::asio::posix::stream_descriptor::wait_type waitType);
        void handleFdEvent();
        void writeSomeFrames();
        void onDrainComplete();

        boost::asio::io_context& _ioContext;
        const std::string _name;
        const PcmParameters _outputParameters;
        boost::asio::io_context::strand _strand;
        SndPcmPtr _pcm;

        std::vector<::pollfd> _fileDescriptors;
        std::vector<boost::asio::posix::stream_descriptor> _streamDescriptors;

        struct WriteOperation
        {
            std::span<const std::byte> buffer;
            WriteCompletionCallback callback;
        };
        std::deque<WriteOperation> _operations;
        std::size_t _totalWrittenFrameCount{};

        bool _drainRequested{};
        DrainCompletionCallback _drainCallback;
        std::thread _drainThread;
    };
} // namespace lms::audio::alsa