/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

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
#include "services/mumaoutbox/IMumaOutboxRelay.hpp"

namespace lms::mumaOutbox
{
    // Which outbox a row lives in. Each has its own table and its own URL at music-manager.
    enum class Table
    {
        Listen,
        Rating,
    };

    // The relay behind IMumaOutboxRelay: delivers the rows of both outboxes to music-manager,
    // oldest first across the two tables, one at a time, and removes each once music-manager
    // has it (docs/designs/lms-rating-outbox/technical.md, "One relay for both outboxes").
    //
    // Everything but the enqueue writes runs on the io_context through a strand, never on a Wt
    // request thread. The relay has its own HTTP client, and with it its own send queue, so a
    // backlog here never waits in -- or holds up -- the /muma proxy's queue.
    //
    // Held by shared_ptr: the HTTP callbacks and the retry timer only keep a weak_ptr, so a
    // callback that arrives after stop() finds nothing to call.
    class MumaOutboxRelay final : public std::enable_shared_from_this<MumaOutboxRelay>
    {
    public:
        // Sends through `client` (base URL: music-manager's API root) with `apiKey` as X-API-Key.
        // Nothing is sent until start() or an enqueue.
        MumaOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey, MumaOutboxSettings settings);
        ~MumaOutboxRelay();

        MumaOutboxRelay(const MumaOutboxRelay&) = delete;
        MumaOutboxRelay& operator=(const MumaOutboxRelay&) = delete;

        // Logs what a previous run left in the outboxes and wakes the relay.
        void start();
        // Writes one listen and wakes the relay. Returns once the row is committed.
        void enqueueListen(std::string_view payload);
        // Writes the latest state of one rating, replacing a waiting one, and wakes the relay.
        void enqueueRating(const RatingKey& key, std::string_view payload);
        // Stops sending and releases the HTTP client; rows stay for the next start.
        void stop();

    private:
        // The row on its way to music-manager.
        struct Pending
        {
            Table table{};
            long long id{};
            std::string payload;
            std::string label; // what the row is, for the log
        };
        // What music-manager answered about one row.
        struct Answer
        {
            Table table{};
            long long id{};
            int status{};
        };
        // A row whose delivery failed and that stays in its outbox.
        struct Kept
        {
            Table table{};
            long long id{};
        };

        void wake();
        void sendNext();
        void dropExpired();
        std::optional<Pending> pickNext();
        void send(const Pending& pending);
        void onAnswer(const Answer& answer);
        void onTransportFailure(const Kept& kept);
        void retryLater(std::optional<Kept> kept);
        bool remove(Table table, long long id);

        boost::asio::io_context& _ioContext;
        boost::asio::io_context::strand _strand{ _ioContext }; // protects every member below but _client
        db::IDb& _db;
        const std::string _apiKey;
        const MumaOutboxSettings _settings;

        std::mutex _clientMutex; // protects _client, which stop() takes away from another thread
        std::unique_ptr<core::http::IClient> _client;
        bool _stopped{};

        boost::asio::steady_timer _retryTimer{ _ioContext };
        bool _inFlight{};
        std::string _inFlightLabel;
        bool _retryPending{};
        std::size_t _consecutiveFailures{};
    };
} // namespace lms::mumaOutbox
