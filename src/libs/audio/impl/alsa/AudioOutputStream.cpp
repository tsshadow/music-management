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

#include "AudioOutputStream.hpp"

#include <cassert>
#include <chrono>
#include <thread>

#include <alsa/asoundlib.h>
#include <boost/asio/bind_executor.hpp>
#include <boost/asio/error.hpp>
#include <boost/asio/post.hpp>

#include "core/ILogger.hpp"

#include "audio/Exception.hpp"

namespace lms::audio::alsa
{
    namespace detail
    {
        ::snd_pcm_format_t toSndPcmFormat(PcmSampleType sampleType, std::endian byteOrder)
        {
            switch (sampleType)
            {
            case PcmSampleType::Signed16:
                return byteOrder == std::endian::little ? SND_PCM_FORMAT_S16_LE : SND_PCM_FORMAT_S16_BE;
            case PcmSampleType::Signed32:
                return byteOrder == std::endian::little ? SND_PCM_FORMAT_S32_LE : SND_PCM_FORMAT_S32_BE;
            case PcmSampleType::Float32:
                return byteOrder == std::endian::little ? SND_PCM_FORMAT_FLOAT_LE : SND_PCM_FORMAT_FLOAT_BE;
            case PcmSampleType::Float64:
                return byteOrder == std::endian::little ? SND_PCM_FORMAT_FLOAT64_LE : SND_PCM_FORMAT_FLOAT64_BE;
            }

            throw Exception{ "Unexpected sample type!" };
        }
    } // namespace detail

    void SndPcmDeleter::operator()(snd_pcm_t* pcm) const noexcept
    {
        const int error{ ::snd_pcm_close(pcm) };
        LMS_LOG_IF(AUDIO_OUTPUT_STREAM, ERROR, error != 0, "snd_pcm_close failed: " << ::snd_strerror(error));

        // TODO move this
        ::snd_config_update_free_global();
    }

    class AlsaException : public Exception
    {
    public:
        AlsaException(std::string_view msg, int error)
            : Exception{ std::string{ msg } + ": " + ::snd_strerror(error) }
        {
        }
    };

    AudioOutputStream::AudioOutputStream(boost::asio::io_context& ioContext, std::string_view device, std::string_view name, const PcmParameters& outputParameters)
        : _ioContext{ ioContext }
        , _name{ name }
        , _outputParameters{ outputParameters }
        , _strand{ _ioContext }
    {
        if (_outputParameters.planar)
            throw Exception{ "Planar output format not supported" };

        {
            snd_pcm_t* pcm{};
            const int error{ ::snd_pcm_open(&pcm, std::string{ device }.c_str(), SND_PCM_STREAM_PLAYBACK, 0) };
            if (error != 0)
                throw AlsaException{ "snd_pcm_open failed", error };

            _pcm = SndPcmPtr{ pcm };
        }

        {
            ::snd_pcm_hw_params_t* hw_params{};
            snd_pcm_hw_params_alloca(&hw_params);
            ::snd_pcm_hw_params_any(_pcm.get(), hw_params);

            ::snd_pcm_hw_params_set_access(_pcm.get(), hw_params, SND_PCM_ACCESS_RW_INTERLEAVED);
            ::snd_pcm_hw_params_set_format(_pcm.get(), hw_params, detail::toSndPcmFormat(_outputParameters.sampleType, outputParameters.byteOrder));
            ::snd_pcm_hw_params_set_channels(_pcm.get(), hw_params, _outputParameters.channelCount);
            ::snd_pcm_hw_params_set_rate(_pcm.get(), hw_params, _outputParameters.sampleRate, 1);

            // TODO fragile!!
            {
                constexpr std::chrono::milliseconds wantedBufferDuration{ 500 }; // should be enough...
                int dir{};
                unsigned int bufferDuration{ std::chrono::duration_cast<std::chrono::microseconds>(wantedBufferDuration).count() };
                const int error{ ::snd_pcm_hw_params_set_buffer_time_near(_pcm.get(), hw_params, &bufferDuration, &dir) };
                if (error < 0)
                    throw AlsaException{ "snd_pcm_hw_params_set_buffer_size failed", error };

                LMS_LOG(AUDIO_OUTPUT_STREAM, DEBUG, ::snd_pcm_name(_pcm.get()) << ", buffer time set to " << bufferDuration << " mus");
            }

            {
                constexpr std::chrono::milliseconds wantedPeriodDuration{ 100 }; // should be enough...
                int dir{};
                unsigned int periodDuration{ std::chrono::duration_cast<std::chrono::microseconds>(wantedPeriodDuration).count() };
                const int error{ ::snd_pcm_hw_params_set_period_time_near(_pcm.get(), hw_params, &periodDuration, &dir) };
                if (error < 0)
                    throw AlsaException{ "snd_pcm_hw_params_set_period_size failed", error };

                LMS_LOG(AUDIO_OUTPUT_STREAM, DEBUG, ::snd_pcm_name(_pcm.get()) << ", period time set to " << periodDuration << " mus");
            }

            const int error{ ::snd_pcm_hw_params(_pcm.get(), hw_params) };
            if (error != 0)
                throw AlsaException{ "snd_pcm_hw_params failed", error };
        }

        {
            ::snd_pcm_sw_params_t* sw{};
            snd_pcm_sw_params_alloca(&sw);

            ::snd_pcm_sw_params_current(_pcm.get(), sw);

            {
                const int error{ ::snd_pcm_sw_params_set_tstamp_mode(_pcm.get(), sw, SND_PCM_TSTAMP_ENABLE) };
                if (error != 0)
                    throw AlsaException{ "snd_pcm_sw_params_set_tstamp_mode failed", error };
            }
            {
                const int error{ ::snd_pcm_sw_params_set_tstamp_type(_pcm.get(), sw, SND_PCM_TSTAMP_TYPE_MONOTONIC) };
                if (error != 0)
                    throw AlsaException{ "snd_pcm_sw_params_set_tstamp_type failed", error };
            }
            {
                const int error{ ::snd_pcm_sw_params(_pcm.get(), sw) };
                if (error != 0)
                    throw AlsaException{ "snd_pcm_sw_params failed", error };
            }
        }

        {
            const int error{ ::snd_pcm_prepare(_pcm.get()) };
            if (error != 0)
                throw AlsaException{ "snd_pcm_prepare failed", error };
        }

        setupAllDescriptors();
    }

    AudioOutputStream::~AudioOutputStream()
    {
        if (_drainThread.joinable())
            _drainThread.join();

        stop();
    }

    const PcmParameters& AudioOutputStream::getParameters() const
    {
        return _outputParameters;
    }

    void AudioOutputStream::asyncWaitReady(WaitReadyCallback cb)
    {
        // Always ready
        boost::asio::post(_ioContext, std::move(cb));
    }

    void AudioOutputStream::asyncWrite(std::span<const std::byte> buffer, WriteCompletionCallback cb)
    {
        if (buffer.size() % (getSampleSize(_outputParameters.sampleType) * _outputParameters.channelCount) != 0)
            throw Exception{ "Unexpected buffer size" };

        boost::asio::post(_strand, [this, buffer, cb = std::move(cb)]() mutable {
            assert(_strand.running_in_this_thread());

            if (_drainRequested)
                throw Exception{ "asyncDrain already called!" };

            WriteOperation operation;
            operation.buffer = buffer;
            operation.callback = std::move(cb);

            _ioContext.get_executor().on_work_started();
            _operations.push_back(std::move(operation));
        });
    }

    void AudioOutputStream::asyncDrain(DrainCompletionCallback cb)
    {
        boost::asio::post(_strand, [this, cb = std::move(cb)]() mutable {
            if (_drainRequested)
                throw Exception{ "asyncDrain already called!" };

            _ioContext.get_executor().on_work_started();

            _drainRequested = true;
            _drainCallback = std::move(cb);
        });
    }

    void AudioOutputStream::pause()
    {
        const int error{ ::snd_pcm_pause(_pcm.get(), 0) };
        if (error < 0)
            throw AlsaException{ "snd_pcm_pause(0) failed", error };
    }

    void AudioOutputStream::resume()
    {
        // Initial case (no auto play)
        if (::snd_pcm_state(_pcm.get()) == SND_PCM_STATE_PREPARED)
        {
            boost::asio::post(_strand, [this] { asyncWaitAllDescriptors(); });
            return;
        }

        const int error{ ::snd_pcm_pause(_pcm.get(), 1) };
        if (error < 0)
            throw AlsaException{ "snd_pcm_pause(1) failed", error };
    }

    bool AudioOutputStream::isPaused() const
    {
        return ::snd_pcm_state(_pcm.get()) == SND_PCM_STATE_PAUSED;
    }

    void AudioOutputStream::setVolume(float)
    {
    }

    float AudioOutputStream::getVolume() const
    {
        return 1.F;
    }

    std::chrono::microseconds AudioOutputStream::getPlaybackTime() const
    {
        ::snd_pcm_sframes_t delayFrames{};

        const int error{ ::snd_pcm_delay(_pcm.get(), &delayFrames) };
        if (error != 0)
        {
            LMS_LOG(AUDIO_OUTPUT_STREAM, WARNING, "snd_pcm_delay failed: " << snd_strerror(error));
            delayFrames = 0;
        }

        assert(static_cast<snd_pcm_sframes_t>(_totalWrittenFrameCount) >= delayFrames);
        const snd_pcm_sframes_t playedFrameCount{ static_cast<snd_pcm_sframes_t>(_totalWrittenFrameCount) - delayFrames };

        return std::chrono::microseconds{ playedFrameCount * std::chrono::microseconds::period::den / _outputParameters.sampleRate };
    }

    std::chrono::microseconds AudioOutputStream::getLatency() const
    {
        ::snd_pcm_sframes_t delayFrames{};

        const int error{ ::snd_pcm_delay(_pcm.get(), &delayFrames) };
        if (error != 0)
        {
            LMS_LOG(AUDIO_OUTPUT_STREAM, WARNING, "snd_pcm_delay failed: " << snd_strerror(error));
            delayFrames = 0;
        }

        return std::chrono::microseconds{ delayFrames * std::chrono::microseconds::period::den / _outputParameters.sampleRate };
    }

    void AudioOutputStream::flush()
    {
        boost::asio::post(_strand, [this] {
            assert(_strand.running_in_this_thread());

            LMS_LOG(AUDIO_OUTPUT_STREAM, DEBUG, "Flushing output");

            if (_drainRequested)
                throw Exception{ "asyncDrain already called!" };
#if 0
            {
                const int error{ ::snd_pcm_drop(_pcm.get()) };
                if (error < 0)
                    throw AlsaException{ "snd_pcm_drop failed", error };
            }

            {
                const int error{ ::snd_pcm_prepare(_pcm.get()) };
                if (error < 0)
                    throw AlsaException{ "snd_pcm_prepare failed", error };
            }
#endif
            while (!_operations.empty())
            {
                WriteOperation& operation{ _operations.front() };

                boost::asio::post(_ioContext, std::move(operation.callback));
                _ioContext.get_executor().on_work_finished();

                _operations.pop_front();
            }
        });
    }

    void AudioOutputStream::stop()
    {
        releaseAllDescriptors();
        _pcm.reset();
    }

    void AudioOutputStream::setupAllDescriptors()
    {
        const int fdCount{ ::snd_pcm_poll_descriptors_count(_pcm.get()) };
        _fileDescriptors.resize(fdCount);

        const int error{ ::snd_pcm_poll_descriptors(_pcm.get(), _fileDescriptors.data(), _fileDescriptors.size()) };
        if (error < 0)
            throw AlsaException{ "snd_pcm_poll_descriptors failed", error };

        for (const ::pollfd& fd : _fileDescriptors)
            _streamDescriptors.emplace_back(_ioContext, fd.fd);
    }

    void AudioOutputStream::releaseAllDescriptors()
    {
        for (auto& streamDescriptor : _streamDescriptors)
            streamDescriptor.release();

        _streamDescriptors.clear();
    }

    void AudioOutputStream::asyncWaitAllDescriptors()
    {
        assert(_strand.running_in_this_thread());

        for (std::size_t i{}; i < _fileDescriptors.size(); ++i)
        {
            if (_fileDescriptors[i].events & POLLOUT)
                asyncWaitDescriptor(_streamDescriptors[i], boost::asio::posix::stream_descriptor::wait_write);
            if (_fileDescriptors[i].events & POLLIN)
                asyncWaitDescriptor(_streamDescriptors[i], boost::asio::posix::stream_descriptor::wait_read);
        }
    }

    void AudioOutputStream::cancelAllDescriptors()
    {
        assert(_strand.running_in_this_thread());

        for (std::size_t i{}; i < _fileDescriptors.size(); ++i)
        {
            if (_fileDescriptors[i].events & (POLLOUT | POLLIN))
                _streamDescriptors[i].cancel();
        }
    }

    void AudioOutputStream::asyncWaitDescriptor(boost::asio::posix::stream_descriptor& streamDescriptor, boost::asio::posix::stream_descriptor::wait_type waitType)
    {
        auto waitCallback{ [this, &streamDescriptor, waitType](const boost::system::error_code& ec) {
            assert(_strand.running_in_this_thread());

            if (ec == boost::asio::error::operation_aborted)
                return;

            if (ec)
            {
                LMS_LOG(AUDIO_OUTPUT_STREAM, ERROR, "Poll failed: " << ec);
                throw Exception{ "poll failed: " + ec.message() };
            }

            unsigned short revents{};
            ::snd_pcm_poll_descriptors_revents(_pcm.get(), _fileDescriptors.data(), _fileDescriptors.size(), &revents);
            if (revents & POLLERR)
                LMS_LOG(AUDIO_OUTPUT_STREAM, ERROR, "snd_pcm_poll_descriptors_revents raied error!");
            if (revents & POLLOUT)
                writeSomeFrames();

            if (_drainRequested && _operations.empty())
            {
                cancelAllDescriptors();

                _drainThread = std::thread{ [this] {
                    const int error{ ::snd_pcm_drain(_pcm.get()) };
                    if (error != 0)
                        throw AlsaException{ "snd_pcm_drain failed: ", error };

                    boost::asio::post(_strand, [this] { onDrainComplete(); });
                } };
            }
            else
                asyncWaitDescriptor(streamDescriptor, waitType);
        } };

        streamDescriptor.async_wait(waitType, boost::asio::bind_executor(_strand, std::move(waitCallback)));
    }

    void AudioOutputStream::writeSomeFrames()
    {
        assert(_strand.running_in_this_thread());

        while (!_operations.empty())
        {
            WriteOperation& operation{ _operations.front() };

            snd_pcm_sframes_t availableFrameCount{ ::snd_pcm_avail(_pcm.get()) };
            std::size_t frameCount{ operation.buffer.size() / (getSampleSize(_outputParameters.sampleType) * _outputParameters.channelCount) };

            if (frameCount > static_cast<std::size_t>(availableFrameCount))
                frameCount = availableFrameCount;

            const ::snd_pcm_sframes_t writtenFrameCount{ ::snd_pcm_writei(_pcm.get(), operation.buffer.data(), frameCount) };
            if (writtenFrameCount < 0)
            {
                LMS_LOG(AUDIO_OUTPUT_STREAM, WARNING, ::snd_pcm_name(_pcm.get()) << ", recovery needed! error = " << snd_strerror(writtenFrameCount) << ", pcm state = " << ::snd_pcm_state_name(::snd_pcm_state(_pcm.get())));
                const int error{ ::snd_pcm_recover(_pcm.get(), static_cast<int>(writtenFrameCount), 1) };
                if (error)
                    throw AlsaException{ "Unrecoverable error", error };
            }

            const std::size_t writtenByteCount{ writtenFrameCount * getSampleSize(_outputParameters.sampleType) * _outputParameters.channelCount };
            assert(writtenFrameCount <= static_cast<::snd_pcm_sframes_t>(frameCount));
            _totalWrittenFrameCount += writtenFrameCount;

            operation.buffer = std::span<const std::byte>{ operation.buffer.data() + writtenByteCount, operation.buffer.size() - writtenByteCount };
            if (!operation.buffer.empty())
                break;

            boost::asio::post(_ioContext, std::move(operation.callback));
            _ioContext.get_executor().on_work_finished();

            _operations.pop_front();
        }
    }

    void AudioOutputStream::onDrainComplete()
    {
        assert(_strand.running_in_this_thread());

        boost::asio::post(_ioContext, std::move(_drainCallback));
        _ioContext.get_executor().on_work_finished();

        stop();
    }
} // namespace lms::audio::alsa