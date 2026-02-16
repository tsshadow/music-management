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

#include <deque>
#include <list>
#include <vector>

#include "audio/IAudioOutput.hpp"

extern "C"
{
    struct pa_context;
    struct pa_proplist;
    struct pa_stream;
    struct pa_threaded_mainloop;
}

namespace lms::audio::pulseaudio
{
    struct PaPropListDeleter
    {
        void operator()(pa_proplist* proplist) const noexcept;
    };
    using PaPropListPtr = std::unique_ptr<pa_proplist, PaPropListDeleter>;

    struct PaStreamDeleter
    {
        void operator()(pa_stream* stream) const noexcept;
    };
    using PaStreamPtr = std::unique_ptr<pa_stream, PaStreamDeleter>;

    class AudioOutputStream : public IAudioOutputStream
    {
    public:
        AudioOutputStream(boost::asio::io_context& ioContext, pa_context* context, pa_threaded_mainloop* mainLoop, std::string_view name, const PcmParameters& outputParameters);
        ~AudioOutputStream() override;

        AudioOutputStream(AudioOutputStream&) = delete;
        AudioOutputStream& operator=(AudioOutputStream&) = delete;

    private:
        const PcmParameters& getParameters() const override;
        void asyncWaitReady(WaitReadyCallback cb) override;
        void asyncWrite(std::span<const std::byte> buffer, WriteCompletionCallback cb) override;
        void asyncDrain(DrainCompletionCallback cb) override;

        void pause() override;
        void resume() override;
        bool isPaused() const override;

        std::chrono::microseconds getPlaybackTime() const override;
        std::chrono::microseconds getLatency() const override;

        void flush() override;

        void connect();
        void onStateChanged();
        void onWriteRequested(std::size_t writableSize);
        void writeSome(std::size_t writableSize);
        void drain();
        void onDrainComplete(bool success);

        boost::asio::io_context& _ioContext;
        pa_context* _context;
        pa_threaded_mainloop* _mainLoop;
        const PcmParameters _outputParameters;
        PaStreamPtr _stream;

        WaitReadyCallback _waitReadyCallback;

        using WriteOperationId = std::size_t;
        struct WriteOperation
        {
            WriteOperationId id{};
            AudioOutputStream* stream{};
            std::span<const std::byte> buffer;
            WriteCompletionCallback callback;
        };
        WriteOperationId _nextWriteOperationId{};
        std::list<WriteOperation> _operations; // we want obj addresses to be stable
        std::vector<WriteOperation*> _freeOperations;
        std::deque<WriteOperation*> _pendingWriteOperations;
        std::size_t _ongoingWriteOperationCount{};

        WriteOperation* acquireWriteOperation();
        void releaseWriteOperation(WriteOperation* operation);

        void onWriteOperationComplete(WriteOperation* operation);
        void onPartialWriteOperationComplete(WriteOperation* operation);
        void onWriteOperationCancelled(WriteOperation* operation);

        bool _drainRequested{};
        bool _drainDone{};
        DrainCompletionCallback _drainCallback;
    };
} // namespace lms::audio::pulseaudio