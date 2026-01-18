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

#include <boost/program_options.hpp>

#include "core/ILogger.hpp"

#include "audio/Exception.hpp"
#include "audio/IPcmDecoder.hpp"

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
            ("output",program_options::value<std::string>()->required(), "Output audio file path");
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
        std::filesystem::path outputPath{ vm["output"].as<std::string>() };
        if (!std::filesystem::exists(inputPath))
            throw std::runtime_error{ "File '" + inputPath.string() + "' does not exist!" };

        core::Service<core::logging::ILogger> logger{ core::logging::createLogger(core::logging::Severity::DEBUG) };

        try
        {
            audio::PcmDecoderParameters decoderParams;
            decoderParams.byteOrder = std::endian::little;
            decoderParams.channelCount = 2;
            decoderParams.sampleRate = 48000;
            decoderParams.planar = true;
            decoderParams.sampleType = audio::PcmDecodeSampleType::Float32;

            auto decoder{ audio::createPcmDecoder(inputPath, decoderParams) };

            using Buffer = std::vector<std::byte>;

            std::array<Buffer, 2> channelBuffers;
            constexpr std::chrono::milliseconds bufferDuration{ 50 };
            const std::size_t sampleCountPerChannel{ static_cast<std::size_t>(std::chrono::duration_cast<std::chrono::microseconds>(bufferDuration).count() * decoderParams.sampleRate / std::chrono::microseconds::period::den) };
            std::cout << "Using buffer size of " << sampleCountPerChannel << " samples per channel" << std::endl;
            for (auto& buffer : channelBuffers)
                buffer.resize(sampleCountPerChannel * sizeof(float));

            std::size_t totalSampleCount{ 0 };
            while (!decoder->finished())
            {
                std::array outputBuffers{
                    std::span<std::byte>{ channelBuffers[0].data(), channelBuffers[0].size() },
                    std::span<std::byte>{ channelBuffers[1].data(), channelBuffers[1].size() }
                };
                const std::size_t sampleCount{ decoder->readSamples(outputBuffers) };
                totalSampleCount += sampleCount;
            }

            std::cout << "Decoding finished, total samples per channel: " << totalSampleCount << std::endl;
            std::cout << "Estimated duration: " << static_cast<double>(totalSampleCount) / static_cast<double>(decoderParams.sampleRate) << " seconds" << std::endl;
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