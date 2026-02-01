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
#include <iostream>

#include <boost/asio/io_context.hpp>
#include <boost/asio/post.hpp>
#include <boost/program_options.hpp>

#include "core/ILogger.hpp"
#include "core/String.hpp"

#include "audio/Exception.hpp"
#include "audio/IAudioOutput.hpp"
#include "audio/IPcmDecoder.hpp"
#include "audio/PcmTypes.hpp"

namespace lms
{
    class FilePlayer
    {
    public:
        FilePlayer(boost::asio::io_context& ioContext, audio::IAudioOutputContext& context, const std::filesystem::path& filePath, const audio::PcmParameters& params)
            : _ioContext{ ioContext }
            , _context{ context }
            , _pcmDecoder{ audio::createPcmDecoder(filePath, params) }
        {
            _context.asyncWaitReady([this] {
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
            _outputStream = _context.createOutputStream("LMS-player", getPcmParameters());

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

            _buffers.resize(bufferCount);
            for (BufferDesc& bufferDesc : _buffers)
                bufferDesc.buffer.resize(bufferSize);
        }

        void decodeSome()
        {
            while (!_draining)
            {
                BufferDesc& bufferDesc{ _buffers[_nextBufferIndex] };
                if (bufferDesc.isInWrite)
                    break;

                const std::size_t bufferIndex{ _nextBufferIndex };
                if (++_nextBufferIndex >= _buffers.size())
                    _nextBufferIndex = 0;

                std::span<std::byte> buffer{ bufferDesc.buffer };
                const std::size_t sampleCount{ readSamples(buffer) };
                if (sampleCount == 0) // EOF
                {
                    _draining = true;
                    _outputStream->asyncDrain([this] {});
                    break;
                }

                bufferDesc.isInWrite = true;
                buffer = { buffer.data(), sampleCountToByteCount(sampleCount) };

                _outputStream->asyncWrite(buffer, [this, bufferIndex] {
                    onBufferWriteComplete(bufferIndex);
                });

                boost::asio::post(_ioContext, [this] { decodeSome(); });
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
        audio::IAudioOutputContext& _context;
        std::unique_ptr<audio::IPcmDecoder> _pcmDecoder;
        std::unique_ptr<audio::IAudioOutputStream> _outputStream;

        struct BufferDesc
        {
            using Buffer = std::vector<std::byte>;
            Buffer buffer;
            bool isInWrite{};
        };
        static constexpr std::size_t bufferCount{ 4 };
        std::vector<BufferDesc> _buffers;
        std::size_t _nextBufferIndex{};
        std::size_t _sampleCountPerBuffer{};
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
            ("input",program_options::value<std::string>()->required(), "Input audio file path")
            ("backend", program_options::value<std::string>()->default_value(std::string{ "auto" }, "auto"), "Backend to be used (value can be \"alsa\", \"pulseaudio\")");
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

        audio::AudioOutputBackend outputBackend;
        if (core::stringUtils::stringCaseInsensitiveEqual(vm["backend"].as<std::string>(), "alsa"))
            outputBackend = audio::AudioOutputBackend::ALSA;
        else if (core::stringUtils::stringCaseInsensitiveEqual(vm["backend"].as<std::string>(), "pulseaudio"))
            outputBackend = audio::AudioOutputBackend::PulseAudio;
        else if (core::stringUtils::stringCaseInsensitiveEqual(vm["backend"].as<std::string>(), "auto"))
        {
            const auto backends{ audio::getAudioOutputBackends() };
            if (backends.contains(audio::AudioOutputBackend::PulseAudio))
                outputBackend = audio::AudioOutputBackend::PulseAudio;
            else if (backends.contains(audio::AudioOutputBackend::ALSA))
                outputBackend = audio::AudioOutputBackend::ALSA;
            else
                throw std::runtime_error{ "No audio output backend available!" };
        }
        else
            throw program_options::validation_error{ program_options::validation_error::invalid_option_value, "backend" };

        core::Service<core::logging::ILogger> logger{ core::logging::createLogger(core::logging::Severity::INFO) };

        try
        {
            audio::PcmParameters decoderParams;
            decoderParams.byteOrder = std::endian::little;
            decoderParams.channelCount = 2;
            decoderParams.sampleRate = 44100;
            decoderParams.planar = false;
            decoderParams.sampleType = audio::PcmSampleType::Signed16;

            const auto availableBackends{ audio::getAudioOutputBackends() };
            if (availableBackends.empty())
                throw std::runtime_error{ "No audio output backend available" };

            boost::asio::io_context context;
            auto audioOutputContext{ audio::createAudioOutputContext(context, "LMS", outputBackend) };

            FilePlayer filePlayer{ context, *audioOutputContext, inputPath, decoderParams };

            context.run();
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
