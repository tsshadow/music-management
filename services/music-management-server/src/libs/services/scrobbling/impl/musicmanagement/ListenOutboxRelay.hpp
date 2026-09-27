/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <chrono>
#include <cstddef>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>

#include <boost/asio/io_context.hpp>
#include <boost/asio/io_context_strand.hpp>
#include <boost/asio/steady_timer.hpp>

#include "core/http/IClient.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::scrobbling::musicManagement
{
    // How long and how much the outbox keeps, and how patiently it retries.
    // docs/designs/lms-listen-outbox/technical.md explains the numbers.
    struct ListenOutboxSettings
    {
        // Beyond this many waiting listens the oldest are dropped, with a WARNING.
        std::size_t maxCount{ 10'000 };
        // A listen still undelivered after this long is dropped, with a WARNING.
        std::chrono::seconds maxAge{ std::chrono::hours{ 24 * 14 } };
        // Wait after the first failed delivery; doubled on each further failure, up to maxRetryDelay.
        std::chrono::milliseconds minRetryDelay{ std::chrono::seconds{ 5 } };
        std::chrono::milliseconds maxRetryDelay{ std::chrono::seconds{ 60 } };
    };

    // Delivers the listens waiting in lms.db's muma_listen_outbox to music-manager, oldest first,
    // one at a time, and removes each once music-manager has it.
    //
    // Everything runs on the io_context through a strand, never on a Wt request thread: a
    // request only writes the row (enqueue) and wakes the relay. The relay has its own HTTP
    // client, and with it its own send queue, so a backlog here never waits in -- or holds up --
    // the /muma proxy's queue.
    //
    // Held by shared_ptr: the HTTP callbacks and the retry timer only keep a weak_ptr, so a
    // callback that arrives after stop() finds nothing to call.
    class ListenOutboxRelay final : public std::enable_shared_from_this<ListenOutboxRelay>
    {
    public:
        // Sends through `client` with `apiKey` as X-API-Key. Nothing happens until start().
        ListenOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey, ListenOutboxSettings settings);
        ~ListenOutboxRelay();

        ListenOutboxRelay(const ListenOutboxRelay&) = delete;
        ListenOutboxRelay& operator=(const ListenOutboxRelay&) = delete;

        // Resumes whatever a previous run of LMS left in the outbox.
        void start();

        // Writes one listen (its JSON body) to the outbox and wakes the relay. Called on the
        // thread that recorded the listen; returns as soon as the row is committed.
        void enqueue(std::string_view payload);

        // Stops sending and releases the HTTP client. Rows still waiting stay in the outbox for
        // the next start. Called once, by the owner, before letting go of the relay.
        void stop();

    private:
        void wake();
        void sendNext();
        // What music-manager answered about one outbox row.
        struct Answer
        {
            long long id{};
            int status{};
        };
        void onAnswer(const Answer& answer);
        void onTransportFailure(long long id);
        void retryLater(std::optional<long long> id);
        bool remove(long long id);

        boost::asio::io_context& _ioContext;
        boost::asio::io_context::strand _strand{ _ioContext }; // protects every member below but _client
        db::IDb& _db;
        const std::string _apiKey;
        const ListenOutboxSettings _settings;

        std::mutex _clientMutex; // protects _client, which stop() takes away from another thread
        std::unique_ptr<core::http::IClient> _client;
        bool _stopped{};

        boost::asio::steady_timer _retryTimer{ _ioContext };
        bool _inFlight{};
        bool _retryPending{};
        std::size_t _consecutiveFailures{};
    };
} // namespace lms::scrobbling::musicManagement
