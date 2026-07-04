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
#include "core/http/ClientRequestParameters.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/RatedArtist.hpp"
#include "database/objects/RatedRelease.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Release.hpp"
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

    void MusicManagementBackend::onStarred(db::StarredArtistId)
    {
    }
    void MusicManagementBackend::onUnstarred(db::StarredArtistId)
    {
    }
    void MusicManagementBackend::onStarred(db::StarredReleaseId)
    {
    }
    void MusicManagementBackend::onUnstarred(db::StarredReleaseId)
    {
    }
    void MusicManagementBackend::onStarred(db::StarredTrackId)
    {
    }
    void MusicManagementBackend::onUnstarred(db::StarredTrackId)
    {
    }

    void MusicManagementBackend::onRatingChanged(db::RatedArtistId ratedArtistId)
    {
        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        if (auto ratedArtist{ db::RatedArtist::find(session, ratedArtistId) })
        {
            if (auto artist{ ratedArtist->getArtist() })
            {
                std::string artistName = artist->getName();
                int rating = ratedArtist->getRating();

                LMS_LOG(SCROBBLING, DEBUG, "Rating changed for artist " << artistName << " (rating: " << rating << ")");
                sendEvent("rating_changed", "artist", artistName, rating);
            }
        }
    }

    void MusicManagementBackend::onRatingChanged(db::RatedReleaseId ratedReleaseId)
    {
        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        if (auto ratedRelease{ db::RatedRelease::find(session, ratedReleaseId) })
        {
            if (auto release{ ratedRelease->getRelease() })
            {
                std::string releaseName = release->getName();
                int rating = ratedRelease->getRating();

                LMS_LOG(SCROBBLING, DEBUG, "Rating changed for release " << releaseName << " (rating: " << rating << ")");
                sendEvent("rating_changed", "release", releaseName, rating);
            }
        }
    }

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

        core::http::ClientPOSTRequestParameters request;
        request.message.addHeader("Content-Type", "application/json");

        // Simple JSON manual construction
        std::string body = "{";
        body += "\"event\": \"" + eventType + "\",";
        body += "\"object_type\": \"" + objectType + "\",";
        body += "\"object_id\": \"" + objectId + "\",";
        body += "\"rating\": " + std::to_string(rating);
        if (!path.empty())
        {
            body += ",\"path\": \"" + path + "\"";
        }
        body += "}";

        request.message.addBodyText(body);

        request.onSuccessFunc = [](const Wt::Http::Message& msg) {
            if (msg.status() >= 200 && msg.status() < 300)
            {
                LMS_LOG(SCROBBLING, DEBUG, "Successfully sent event to music-management");
            }
            else
            {
                LMS_LOG(SCROBBLING, WARNING, "Failed to send event to music-management, status: " << msg.status());
            }
        };
        request.onFailureFunc = []() {
            LMS_LOG(SCROBBLING, WARNING, "Failed to send event to music-management, connection error");
        };

        _client->sendPOSTRequest(std::move(request));
    }
} // namespace lms::feedback::musicManagement
