/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#include "MusicManagementBackend.hpp"

#include <Wt/Http/Client.h>
#include <Wt/WDateTime.h>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Track.hpp"

namespace lms::feedback::musicManagement
{
    MusicManagementBackend::MusicManagementBackend(boost::asio::io_context& ioContext, db::IDb& db)
        : _ioContext{ ioContext }
        , _db{ db }
        , _apiUrl{ core::Service<core::IConfig>::get()->getString("music-management-api-url", "http://music-management:8080/api/lms-event") }
    {
        LMS_LOG(SCROBBLING, INFO, "Starting MusicManagement feedback backend... API endpoint = '" << _apiUrl << "'");
        _client = core::http::createClient(_ioContext, _apiUrl);
    }

    MusicManagementBackend::~MusicManagementBackend()
    {
        LMS_LOG(SCROBBLING, INFO, "Stopped MusicManagement feedback backend!");
    }

    void MusicManagementBackend::onStarred(db::StarredArtistId) {}
    void MusicManagementBackend::onUnstarred(db::StarredArtistId) {}
    void MusicManagementBackend::onStarred(db::StarredReleaseId) {}
    void MusicManagementBackend::onUnstarred(db::StarredReleaseId) {}
    void MusicManagementBackend::onStarred(db::StarredTrackId) {}
    void MusicManagementBackend::onUnstarred(db::StarredTrackId) {}

    void MusicManagementBackend::onRatingChanged(db::RatedArtistId) {}
    void MusicManagementBackend::onRatingChanged(db::RatedReleaseId) {}

    void MusicManagementBackend::onRatingChanged(db::RatedTrackId ratedTrackId)
    {
        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        if (auto ratedTrack{ db::RatedTrack::find(session, ratedTrackId) })
        {
            if (auto track{ ratedTrack->getTrack() })
            {
                std::string trackId = track->getId().toString();
                int rating = ratedTrack->getRating();
                std::string path = track->getAbsoluteFilePath().string();
                
                LMS_LOG(SCROBBLING, DEBUG, "Rating changed for track " << trackId << " (rating: " << rating << ", path: " << path << ")");
                sendEvent("rating_changed", "track", trackId, rating, path);
            }
        }
    }

    void MusicManagementBackend::sendEvent(const std::string& eventType, const std::string& objectType, const std::string& objectId, int rating, const std::string& path)
    {
        if (!_client)
            return;

        core::http::IClient::Request request;
        request.method = core::http::Method::Post;
        request.url = _apiUrl;
        request.headers["Content-Type"] = "application/json";
        
        // Simple JSON manual construction
        request.body = "{";
        request.body += "\"event\": \"" + eventType + "\",";
        request.body += "\"object_type\": \"" + objectType + "\",";
        request.body += "\"object_id\": \"" + objectId + "\",";
        request.body += "\"rating\": " + std::to_string(rating);
        if (!path.empty()) {
            request.body += ",\"path\": \"" + path + "\"";
        }
        request.body += "}";

        _client->sendRequest(request, [](const core::http::IClient::Response& response) {
            if (response.status >= 200 && response.status < 300) {
                LMS_LOG(SCROBBLING, DEBUG, "Successfully sent event to music-management");
            } else {
                LMS_LOG(SCROBBLING, WARNING, "Failed to send event to music-management, status: " << response.status);
            }
        });
    }
} // namespace lms::feedback::musicManagement
