
/*
 * Copyright (C) 2025 Emeric Poupon
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

#include "FFmpegTypes.hpp"

extern "C"
{
#include <libavcodec/avcodec.h>
#include <libavcodec/packet.h>
#include <libavformat/avformat.h>
#include <libswresample/swresample.h>
}

namespace lms::audio::ffmpeg
{
    void AvCodecContextDeleter::operator()(AVCodecContext* ctx) const noexcept
    {
        if (ctx)
            ::avcodec_free_context(&ctx);
    }

    void AvFormatContextDeleter::operator()(AVFormatContext* ctx) const noexcept
    {
        if (!ctx)
            return;

        ::avformat_close_input(&ctx);
    }

    void AvFrameDeleter::operator()(AVFrame* frame) const noexcept
    {
        if (frame)
            ::av_frame_free(&frame);
    }

    void AVPacketDeleter::operator()(AVPacket* packet) const noexcept
    {
        if (packet)
            ::av_packet_free(&packet);
    }

    void SwrContextDeleter::operator()(SwrContext* ctx) const noexcept
    {
        if (ctx)
            ::swr_free(&ctx);
    }
} // namespace lms::audio::ffmpeg