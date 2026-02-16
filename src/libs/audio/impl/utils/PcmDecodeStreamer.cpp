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

#include "PcmDecodeStreamer.hpp"

#include <boost/asio/post.hpp>

#include "audio/Exception.hpp"
#include "core/ILogger.hpp"

#include "audio/IAudioOutput.hpp"
#include "audio/IPcmDecoder.hpp"

namespace lms::audio::utils
{
    std::shared_ptr<IPcmDecodeStreamer> createPcmDecodeStreamer(boost::asio::io_context& ioContext, const PcmDecodeStreamerParameters& parameters)
    {
        return std::make_shared<PcmDecodeStreamer>(ioContext, parameters);
    }

    PcmDecodeStreamer::PcmDecodeStreamer(boost::asio::io_context& ioContext, const PcmDecodeStreamerParameters& parameters)
        : _ioContext{ ioContext }
        , _strand{ _ioContext }
        , _outputStream{ parameters.outputStream }
        , _pcmDecoder{ audio::createPcmDecoder(parameters.file, parameters.offset, parameters.pcmParameters) }
    {
        prepareBuffers();
    }

    PcmDecodeStreamer::~PcmDecodeStreamer()
    {
        assert(!isWritePending());
    }

    void PcmDecodeStreamer::start(DecodeCompleteCallback cb)
    {
        assert(cb);
        assert(!_decodeCompleteCallback);

        _ioContext.get_executor().on_work_started();
        _decodeCompleteCallback = std::move(cb);

        boost::asio::post(_strand, [self = shared_from_this()] {
            self->decodeSome();
        });
    }

    void PcmDecodeStreamer::abort()
    {
        boost::asio::post(_strand, [self = shared_from_this()] {
            LMS_LOG(AUDIO, DEBUG, "Processing abort");
            self->_aborted = true;
            self->_outputStream.flush();

            if (!self->isWritePending())
                self->notifyDecodeComplete();
        });
    }

    const audio::PcmParameters& PcmDecodeStreamer::getPcmParameters() const
    {
        return _pcmDecoder->getParameters();
    }

    void PcmDecodeStreamer::prepareBuffers()
    {
        constexpr std::chrono::milliseconds bufferDuration{ 100 };

        const audio::PcmParameters& pcmParams{ getPcmParameters() };
        std::size_t sampleCountPerBuffer{ static_cast<std::size_t>(std::chrono::duration_cast<std::chrono::microseconds>(bufferDuration).count() * pcmParams.sampleRate / std::chrono::microseconds::period::den) };
        const std::size_t bufferSize{ sampleCountToByteCount(sampleCountPerBuffer) };

        _buffers.resize(bufferCount);
        for (BufferDesc& bufferDesc : _buffers)
            bufferDesc.buffer.resize(bufferSize);
    }

    bool PcmDecodeStreamer::isWritePending() const
    {
        return std::any_of(std::cbegin(_buffers), std::cend(_buffers), [](const BufferDesc& bufferDesc) {
            return bufferDesc.isWritePending;
        });
    }

    void PcmDecodeStreamer::decodeSome()
    {
        assert(_strand.running_in_this_thread());

        while (!_eofReached && !_aborted)
        {
            BufferDesc& bufferDesc{ _buffers[_nextBufferIndex] };
            if (bufferDesc.isWritePending)
                break;

            const std::size_t bufferIndex{ _nextBufferIndex };
            if (++_nextBufferIndex >= _buffers.size())
                _nextBufferIndex = 0;

            std::span<std::byte> buffer{ bufferDesc.buffer };
            const std::size_t sampleCount{ readSamples(buffer) };
            if (sampleCount == 0) // EOF
            {
                LMS_LOG(AUDIO, DEBUG, "EOF reached");
                _eofReached = true;
                if (!isWritePending())
                    notifyDecodeComplete();

                break;
            }

            bufferDesc.isWritePending = true;
            buffer = { buffer.data(), sampleCountToByteCount(sampleCount) };

            _outputStream.asyncWrite(buffer, [self = shared_from_this(), bufferIndex] {
                boost::asio::post(self->_strand, [self, bufferIndex] { self->onBufferWriteComplete(bufferIndex); });
            });

            boost::asio::post(_strand, [self = shared_from_this()] { self->decodeSome(); });
        }
    }

    std::size_t PcmDecodeStreamer::readSamples(std::span<std::byte> buffer)
    {
        assert(_strand.running_in_this_thread());

        try
        {
            std::size_t totalSampleCount{};

            // Buffer must be multiple of sample
            assert(buffer.size() % (audio::getSampleSize(getPcmParameters().sampleType) * getPcmParameters().channelCount) == 0);

            while (!buffer.empty())
            {
                std::array outputBuffers{ audio::IPcmDecoder::WritableBuffer{ buffer } };
                const std::size_t sampleCount{ _pcmDecoder->readSamples(outputBuffers) };
                if (sampleCount == 0)
                    break;

                const std::size_t offset{ sampleCountToByteCount(sampleCount) };
                buffer = std::span<std::byte>{ buffer.data() + offset, buffer.size() - offset };

                totalSampleCount += sampleCount;
            }

            return totalSampleCount;
        }
        catch (const audio::Exception& e)
        {
            LMS_LOG(AUDIO, ERROR, "Failed to read pcm samples: " << e.what());
            return 0;
        }
    }

    void PcmDecodeStreamer::onBufferWriteComplete(std::size_t bufferIndex)
    {
        assert(_strand.running_in_this_thread());

        BufferDesc& bufferDesc{ _buffers[bufferIndex] };

        assert(bufferDesc.isWritePending);
        bufferDesc.isWritePending = false;

        if (!_aborted && !_eofReached)
            decodeSome();
        else if (!isWritePending())
            notifyDecodeComplete();
    }

    void PcmDecodeStreamer::notifyDecodeComplete()
    {
        boost::asio::post(_ioContext, [self = shared_from_this(), cb = std::move(_decodeCompleteCallback)] {
            LMS_LOG(AUDIO, DEBUG, "Decode complete notification");
            cb(self->_aborted);
            self->_ioContext.get_executor().on_work_finished();
        });
    }

    std::size_t PcmDecodeStreamer::sampleCountToByteCount(std::size_t sampleCount) const
    {
        return sampleCount * audio::getSampleSize(getPcmParameters().sampleType) * getPcmParameters().channelCount;
    }
} // namespace lms::audio::utils