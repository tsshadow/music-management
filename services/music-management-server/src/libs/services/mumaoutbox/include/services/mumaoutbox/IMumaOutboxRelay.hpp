/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <chrono>
#include <cstddef>
#include <memory>
#include <string>
#include <string_view>

#include <boost/asio/io_context.hpp>

#include "core/http/IClient.hpp"
#include "database/MumaRatingOutbox.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::mumaOutbox
{
    // What a rating change belongs to: user, object type and id. A newer change for the same key
    // replaces the one still waiting.
    using RatingKey = db::mumaRatingOutbox::Key;

    // How long and how much the outboxes keep, and how patiently the relay retries.
    // docs/designs/lms-listen-outbox/ and docs/designs/lms-rating-outbox/ explain the numbers.
    struct MumaOutboxSettings
    {
        // Beyond this many waiting listens the oldest are dropped, with a WARNING.
        std::size_t listenMaxCount{ 10'000 };
        // A listen still undelivered after this long is dropped, with a WARNING.
        std::chrono::seconds listenMaxAge{ std::chrono::hours{ 24 * 14 } };
        // Beyond this many waiting rating changes the oldest are dropped, each with a WARNING.
        std::size_t ratingMaxCount{ 10'000 };
        // A rating change still undelivered after this long is dropped, with a WARNING.
        std::chrono::seconds ratingMaxAge{ std::chrono::hours{ 24 * 14 } };
        // Wait after the first failed delivery; doubled on each further failure, up to maxRetryDelay.
        std::chrono::milliseconds minRetryDelay{ std::chrono::seconds{ 5 } };
        std::chrono::milliseconds maxRetryDelay{ std::chrono::seconds{ 60 } };
    };

    // Delivers what LMS owes music-manager -- listens (muma_listen_outbox) and rating changes
    // (muma_rating_outbox) -- oldest first, one request at a time, and removes each row once
    // music-manager has it. A caller only writes a row and returns; the sending happens on the
    // io_context, never on the caller's thread.
    class IMumaOutboxRelay
    {
    public:
        virtual ~IMumaOutboxRelay() = default;

        // Resumes whatever a previous run of LMS left in the outboxes. Called once, after every
        // producer exists.
        virtual void start() = 0;

        // Queues one listen (its JSON body for /scrobble/event) and wakes the relay.
        virtual void enqueueListen(std::string_view payload) = 0;

        // Queues the latest state of one rating (its JSON body for /rating/lms-event), replacing
        // a change still waiting for the same key, and wakes the relay.
        virtual void enqueueRating(const RatingKey& key, std::string_view payload) = 0;

        // Stops sending and releases the HTTP client. Rows still waiting stay for the next start.
        virtual void stop() = 0;
    };

    // The relay to `music-management-url`, with `music-management-api-key` as X-API-Key. Null
    // when no music-management-url is configured: then nothing is relayed.
    std::unique_ptr<IMumaOutboxRelay> createMumaOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db);

    // The relay sending through `client`, whose base URL is music-manager's API root. What the
    // configured factory delegates to, and what the tests use with a fake client.
    std::unique_ptr<IMumaOutboxRelay> createMumaOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey, MumaOutboxSettings settings = {});
} // namespace lms::mumaOutbox
