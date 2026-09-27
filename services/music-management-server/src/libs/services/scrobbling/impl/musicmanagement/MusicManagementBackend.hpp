/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <boost/asio/io_context.hpp>
#include <memory>
#include <string>

#include "IScrobblingBackend.hpp"
#include "ListenOutboxRelay.hpp"
#include "core/http/IClient.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::scrobbling::musicManagement
{
    // Relays every finished listen to music-manager's /api/scrobble/event. Each listen is first
    // written to lms.db's outbox and then delivered by a ListenOutboxRelay on the io_context, so
    // an outage of music-manager or a restart of LMS delays a listen instead of losing it
    // (bug report 075, docs/designs/lms-listen-outbox/).
    class MusicManagementBackend final : public IScrobblingBackend
    {
    public:
        MusicManagementBackend(boost::asio::io_context& ioContext, db::IDb& db);
        // Sends through `client` (null switches the relay off) with `apiKey` as X-API-Key.
        // What the configured constructor delegates to, and what the tests use.
        MusicManagementBackend(boost::asio::io_context& ioContext, db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey, ListenOutboxSettings settings = {});
        ~MusicManagementBackend() override;

    private:
        MusicManagementBackend(const MusicManagementBackend&) = delete;
        MusicManagementBackend& operator=(const MusicManagementBackend&) = delete;

        void listenStarted(const Listen& listen) override;
        void listenFinished(const Listen& listen, std::optional<std::chrono::seconds> duration) override;
        void addTimedListen(const TimedListen& listen) override;

        void sendScrobble(const Listen& listen, const Wt::WDateTime& timePoint, std::optional<std::chrono::seconds> duration = std::nullopt);

        db::IDb& _db;
        std::shared_ptr<ListenOutboxRelay> _relay; // null when no client was given
    };
} // namespace lms::scrobbling::musicManagement
