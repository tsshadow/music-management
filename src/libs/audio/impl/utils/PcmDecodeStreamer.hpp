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

#include <filesystem>
#include <memory>
#include <vector>

#include <boost/asio/io_context.hpp>
#include <boost/asio/io_context_strand.hpp>

#include "audio/PcmTypes.hpp"
#include "audio/utils/IPcmDecodeStreamer.hpp"

namespace lms::audio
{
    class IAudioOutputStream;
    class IPcmDecoder;
} // namespace lms::audio

namespace lms::audio::utils
{
    class PcmDecodeStreamer : public IPcmDecodeStreamer, public std::enable_shared_from_this<PcmDecodeStreamer>
    {
    public:
        PcmDecodeStreamer(boost::asio::io_context& ioContext, const PcmDecodeStreamerParameters& parameters);
        ~PcmDecodeStreamer() override;

        PcmDecodeStreamer(const PcmDecodeStreamer&) = delete;
        PcmDecodeStreamer& operator=(const PcmDecodeStreamer&) = delete;

    private:
        void start(DecodeCompleteCallback cb) override;
        void abort() override; // will call DecodeCompleteCallback once done

        const audio::PcmParameters& getPcmParameters() const;

        void prepareBuffers();
        bool isWritePending() const;
        void decodeSome();
        std::size_t readSamples(std::span<std::byte> buffer);
        void onBufferWriteComplete(std::size_t bufferIndex);
        void notifyDecodeComplete();
        std::size_t sampleCountToByteCount(std::size_t sampleCount) const;

        struct BufferDesc
        {
            using Buffer = std::vector<std::byte>;
            Buffer buffer;
            bool isWritePending{};
        };

        boost::asio::io_context& _ioContext;
        boost::asio::io_context::strand _strand;
        audio::IAudioOutputStream& _outputStream;
        std::unique_ptr<audio::IPcmDecoder> _pcmDecoder;

        static constexpr std::size_t bufferCount{ 4 };
        std::vector<BufferDesc> _buffers;
        std::size_t _nextBufferIndex{};
        bool _eofReached{};
        bool _aborted{};

        DecodeCompleteCallback _decodeCompleteCallback;
    };
} // namespace lms::audio::utils