/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#include "MusicManagementBackend.hpp"

#include <Wt/Http/Client.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Value.h>
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
        LMS_LOG(SCROBBLING, INFO, "MusicManagementBackend::onRatingChanged(Artist)");
        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        if (auto ratedArtist{ db::RatedArtist::find(session, ratedArtistId) })
        {
            if (auto artist{ ratedArtist->getArtist() })
            {
                std::string artistName{ artist->getName() };
                int rating = ratedArtist->getRating();

                LMS_LOG(SCROBBLING, INFO, "Rating changed for artist " << artistName << " (rating: " << rating << ")");
                sendEvent("rating_changed", "artist", artistName, rating);
            }
        }
    }

    void MusicManagementBackend::onRatingChanged(db::RatedReleaseId ratedReleaseId)
    {
        LMS_LOG(SCROBBLING, INFO, "MusicManagementBackend::onRatingChanged(Release)");
        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        if (auto ratedRelease{ db::RatedRelease::find(session, ratedReleaseId) })
        {
            if (auto release{ ratedRelease->getRelease() })
            {
                std::string releaseName{ release->getName() };
                int rating = ratedRelease->getRating();

                LMS_LOG(SCROBBLING, INFO, "Rating changed for release " << releaseName << " (rating: " << rating << ")");
                sendEvent("rating_changed", "release", releaseName, rating);
            }
        }
    }

    void MusicManagementBackend::onRatingChanged(db::RatedTrackId ratedTrackId)
    {
        LMS_LOG(SCROBBLING, INFO, "MusicManagementBackend::onRatingChanged(Track)");
        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        if (auto ratedTrack{ db::RatedTrack::find(session, ratedTrackId) })
        {
            if (auto track{ ratedTrack->getTrack() })
            {
                std::string trackId = track->getId().toString();
                int rating = ratedTrack->getRating();
                std::string path = track->getAbsoluteFilePath().string();

                LMS_LOG(SCROBBLING, INFO, "Rating changed for track " << trackId << " (rating: " << rating << ", path: " << path << ")");
                sendEvent("rating_changed", "track", trackId, rating, path);
            }
        }
    }

    void MusicManagementBackend::sendEvent(const std::string& eventType, const std::string& objectType, const std::string& objectId, int rating, const std::string& path)
    {
        LMS_LOG(SCROBBLING, INFO, "MusicManagementBackend::sendEvent(" << eventType << ", " << objectType << ", " << objectId << ", " << rating << ")");
        if (!_client)
        {
            LMS_LOG(SCROBBLING, WARNING, "No HTTP client available!");
            return;
        }

        core::http::ClientPOSTRequestParameters request;
        request.message.addHeader("Content-Type", "application/json");

        Wt::Json::Object obj;
        obj["event"] = Wt::Json::Value(eventType);
        obj["object_type"] = Wt::Json::Value(objectType);
        obj["object_id"] = Wt::Json::Value(objectId);
        obj["rating"] = Wt::Json::Value(rating);
        if (!path.empty())
        {
            obj["path"] = Wt::Json::Value(path);
        }

        std::string jsonBody = Wt::Json::serialize(obj);
        LMS_LOG(SCROBBLING, INFO, "Sending JSON: " << jsonBody);
        request.message.addBodyText(jsonBody);

        request.onSuccessFunc = [](const Wt::Http::Message& msg) {
            if (msg.status() >= 200 && msg.status() < 300)
            {
                LMS_LOG(SCROBBLING, INFO, "Successfully sent event to music-management");
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
