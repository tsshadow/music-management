/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <boost/asio/io_context.hpp>
#include <memory>
#include <string>

#include "IFeedbackBackend.hpp"
#include "core/http/IClient.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::feedback::musicManagement
{
    class MusicManagementBackend final : public IFeedbackBackend
    {
    public:
        MusicManagementBackend(boost::asio::io_context& ioContext, db::IDb& db);
        ~MusicManagementBackend() override;

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

        void sendEvent(const std::string& eventType, const std::string& objectType, const std::string& objectId, const std::string& username, int rating = 0, const std::string& path = "");

        boost::asio::io_context& _ioContext;
        db::IDb& _db;
        std::string _apiUrl;
        std::string _apiKey;
        std::unique_ptr<core::http::IClient> _client;
    };
} // namespace lms::feedback::musicManagement
