/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <string>
#include <string_view>

#include "services/mumaoutbox/IMumaOutboxRelay.hpp"

#include "IFeedbackBackend.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::feedback::musicManagement
{
    // Relays every rating change to music-manager's /api/rating/lms-event. Each change is written
    // to lms.db's rating outbox, replacing a change still waiting for the same item, and then
    // delivered by the shared MuMa outbox relay on the io_context, so an outage of music-manager
    // or a restart of LMS delays a rating instead of losing it (issue #222,
    // docs/designs/lms-rating-outbox/).
    class MusicManagementBackend final : public IFeedbackBackend
    {
    public:
        // Queues through `relay`, which outlives this backend; null switches the relay off.
        MusicManagementBackend(db::IDb& db, mumaOutbox::IMumaOutboxRelay* relay);
        ~MusicManagementBackend() override = default;

    private:
        MusicManagementBackend(const MusicManagementBackend&) = delete;
        MusicManagementBackend& operator=(const MusicManagementBackend&) = delete;

        void onStarred(db::StarredArtistId starredArtistId) override;
        void onUnstarred(db::StarredArtistId starredArtistId) override;
        void onStarred(db::StarredReleaseId starredReleaseId) override;
        void onUnstarred(db::StarredReleaseId starredReleaseId) override;
        void onStarred(db::StarredTrackId starredTrackId) override;
        void onUnstarred(db::StarredTrackId starredTrackId) override;

        void onRatingChanged(db::RatedArtistId artistId) override;
        void onRatingChanged(db::RatedReleaseId releaseId) override;
        void onRatingChanged(db::RatedTrackId trackId) override;
        void onRatingRemoved(const RatingRemovedEvent& event) override;
        void onPlaylistChanged(db::TrackListId playlistId) override;

        // Queues one change of `key` in the rating outbox; `path` only for a track.
        void sendEvent(std::string_view eventType, const mumaOutbox::RatingKey& key, int rating = 0, const std::string& path = "");

        db::IDb& _db;
        mumaOutbox::IMumaOutboxRelay* _relay; // null when no music-management-url is configured
    };
} // namespace lms::feedback::musicManagement
