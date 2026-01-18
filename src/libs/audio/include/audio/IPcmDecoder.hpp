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

#include <bit>
#include <cstddef>
#include <filesystem>
#include <memory>
#include <span>

namespace lms::audio
{
    enum class PcmDecodeSampleType
    {
        Signed16,
        Signed32,
        Float32,
        Float64,
    };

    struct PcmOutputParameters
    {
        unsigned channelCount;
        unsigned sampleRate;
        PcmDecodeSampleType sampleType;
        std::endian byteOrder;
        bool planar;
    };

    class IPcmDecoder
    {
    public:
        virtual ~IPcmDecoder() = default;

        using WritableBuffer = std::span<std::byte>;

        // Returns the number of samples written per channel. Returns 0 only once all remaining samples are drained.
        // Provide one buffer per channel if planar, or a single buffer containing all channels interleaved
        // Each buffer must be sized to hold an integer number of samples according to the requested sample type.
        // For example, for Float32 planar output, each buffer size must be divisible by sizeof(float).
        // The decoder will use the buffer sizes to determine the maximum number of samples it can write.
        virtual std::size_t readSamples(std::span<WritableBuffer> outputChannelBuffers) = 0;
        virtual bool finished() const = 0;
    };

    // Throw on error
    std::unique_ptr<IPcmDecoder> createPcmDecoder(const std::filesystem::path& filePath, const PcmOutputParameters& parameters);
} // namespace lms::audio