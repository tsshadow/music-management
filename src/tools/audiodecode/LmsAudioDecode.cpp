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

#include <bit>
#include <chrono>
#include <format>
#include <iostream>

#include <boost/asio/io_context.hpp>
#include <boost/program_options.hpp>
#include <pulse/def.h>
#include <pulse/error.h>
#include <pulse/sample.h>
#include <pulse/simple.h>

#include "core/ILogger.hpp"

#include "audio/Exception.hpp"
#include "audio/IAudioOutput.hpp"
#include "audio/IPcmDecoder.hpp"
#include "audio/PcmTypes.hpp"

namespace lms
{
    class FilePlayer
    {
    public:
        FilePlayer(boost::asio::io_context& ioContext, const std::filesystem::path& filePath, const audio::PcmParameters& params)
            : _ioContext{ ioContext }
            , _pcmDecoder{ audio::createPcmDecoder(filePath, params) }
            , _context{ audio::createAudioOutputContext(_ioContext, "LMS") }
        {
            _context->asyncWaitReady([this] {
                createStream();
            });
        }
        ~FilePlayer() = default;
        FilePlayer(const FilePlayer&) = delete;
        FilePlayer& operator=(const FilePlayer&) = delete;

    private:
        const audio::PcmParameters& getPcmParameters() const
        {
            return _pcmDecoder->getParameters();
        }

        void createStream()
        {
            _outputStream = _context->createOutputStream("LMS-player", getPcmParameters());

            prepareBuffers();
            decodeSome();

            _outputStream->asyncWaitReady([this] {
                _outputStream->resume();
            });
        }

        void prepareBuffers()
        {
            constexpr std::chrono::milliseconds bufferDuration{ 100 };

            const audio::PcmParameters& pcmParams{ getPcmParameters() };
            _sampleCountPerBuffer = static_cast<std::size_t>(std::chrono::duration_cast<std::chrono::microseconds>(bufferDuration).count() * pcmParams.sampleRate / std::chrono::microseconds::period::den);
            const std::size_t bufferSize{ sampleCountToByteCount(_sampleCountPerBuffer) };
            std::cout << "Using buffer size = " << bufferSize << ", " << _sampleCountPerBuffer << " samples per channel" << std::endl;

            _buffers.resize(4); // TODO parametrize?
            for (BufferDesc& bufferDesc : _buffers)
                bufferDesc.buffer.resize(bufferSize);
        }

        void decodeSome()
        {
            while (!_draining)
            {
                BufferDesc& bufferDesc{ _buffers[_nextBufferIndex] };
                if (bufferDesc.isInWrite)
                    return;

                const std::size_t bufferIndex{ _nextBufferIndex };
                if (++_nextBufferIndex >= _buffers.size())
                    _nextBufferIndex = 0;

                std::span<std::byte> buffer{ bufferDesc.buffer };
                const std::size_t sampleCount{ readSamples(buffer) };
                if (sampleCount == 0)
                {
                    // EOF
                    std::cout << "EOF: draining!" << std::endl;
                    _draining = true;
                    _outputStream->asyncDrain([this] { std::cout << "Drain complete!!" << std::endl; });
                    break;
                }

                bufferDesc.isInWrite = true;
                buffer = { buffer.data(), sampleCountToByteCount(sampleCount) };

                _outputStream->asyncWrite(buffer, [this, bufferIndex] {
                    onBufferWriteComplete(bufferIndex);
                });

                std::cout << "Playback time = " << std::format("{:%T}", std::chrono::duration_cast<std ::chrono::milliseconds>(_outputStream->getPlaybackTime())) << std::endl;

                // TODO, reschedule instead of looping?
            }
        }

        std::size_t readSamples(std::span<std::byte> buffer)
        {
            std::size_t totalSampleCount{};
            while (totalSampleCount < _sampleCountPerBuffer)
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

        void onBufferWriteComplete(std::size_t bufferIndex)
        {
            BufferDesc& bufferDesc{ _buffers[bufferIndex] };

            assert(bufferDesc.isInWrite);
            bufferDesc.isInWrite = false;

            decodeSome();
        }

        std::size_t sampleCountToByteCount(std::size_t sampleCount) const
        {
            return sampleCount * audio::getSampleSize(getPcmParameters().sampleType) * getPcmParameters().channelCount;
        }

        boost::asio::io_context& _ioContext;
        std::unique_ptr<audio::IPcmDecoder> _pcmDecoder;
        std::unique_ptr<audio::IAudioOutputContext> _context;
        std::unique_ptr<audio::IAudioOutputStream> _outputStream;

        struct BufferDesc
        {
            using Buffer = std::vector<std::byte>;
            Buffer buffer;
            bool isInWrite{};
        };
        std::vector<BufferDesc> _buffers;
        std::size_t _nextBufferIndex{};
        std::size_t _sampleCountPerBuffer;
        bool _draining{};
    };
} // namespace lms

int main(int argc, char* argv[])
{
    try
    {
        using namespace lms;
        namespace program_options = boost::program_options;

        program_options::options_description options{ "Options" };
        // clang-format off
        options.add_options()
            ("help,h", "Display this help message")
            ("input",program_options::value<std::string>()->required(), "Input audio file path");
        // clang-format on

        program_options::variables_map vm;
        program_options::store(program_options::parse_command_line(argc, argv, options), vm);

        if (vm.count("help"))
        {
            std::cout << options << "\n";
            return EXIT_SUCCESS;
        }

        // notify required params
        program_options::notify(vm);

        std::filesystem::path inputPath{ vm["input"].as<std::string>() };
        if (!std::filesystem::exists(inputPath))
            throw std::runtime_error{ "File '" + inputPath.string() + "' does not exist!" };

        core::Service<core::logging::ILogger> logger{ core::logging::createLogger(core::logging::Severity::DEBUG) };

        try
        {
            audio::PcmParameters decoderParams;
            decoderParams.byteOrder = std::endian::little;
            decoderParams.channelCount = 2;
            decoderParams.sampleRate = 48000;
            decoderParams.planar = false;
            decoderParams.sampleType = audio::PcmSampleType::Float32;

            boost::asio::io_context context;
            FilePlayer filePlayer{ context, inputPath, decoderParams };

            std::cout << "Running..." << std::endl;
            context.run();
            std::cout << "Running DONE..." << std::endl;
        }
        catch (audio::Exception& e)
        {
            std::cerr << "Caught audio exception: " << e.what() << std::endl;
            return EXIT_FAILURE;
        }
    }
    catch (std::exception& e)
    {
        std::cerr << "Caught exception: " << e.what() << std::endl;
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}
