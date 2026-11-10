/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <string>

#include "IScrobblingBackend.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::mumaOutbox
{
    class IMumaOutboxRelay;
}

namespace lms::scrobbling::musicManagement
{
    // Relays every finished listen to music-manager's /api/scrobble/event. Each listen is written
    // to lms.db's outbox and then delivered by the shared MuMa outbox relay on the io_context, so
    // an outage of music-manager or a restart of LMS delays a listen instead of losing it
    // (bug report 075, docs/designs/lms-listen-outbox/, docs/designs/lms-rating-outbox/).
    class MusicManagementBackend final : public IScrobblingBackend
    {
    public:
        // Queues through `relay`, which outlives this backend; null switches the relay off.
        MusicManagementBackend(db::IDb& db, mumaOutbox::IMumaOutboxRelay* relay);
        ~MusicManagementBackend() override = default;

    private:
        MusicManagementBackend(const MusicManagementBackend&) = delete;
        MusicManagementBackend& operator=(const MusicManagementBackend&) = delete;

        void listenStarted(const Listen& listen) override;
        void listenFinished(const Listen& listen, std::optional<std::chrono::seconds> duration) override;
        void addTimedListen(const TimedListen& listen) override;

        void sendScrobble(const Listen& listen, const Wt::WDateTime& timePoint, std::optional<std::chrono::seconds> duration = std::nullopt);

        db::IDb& _db;
        mumaOutbox::IMumaOutboxRelay* _relay; // null when no music-management-url is configured
    };
} // namespace lms::scrobbling::musicManagement
