/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#include "MusicManagementBackend.hpp"

#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Value.h>
#include <Wt/WDateTime.h>

#include "core/ILogger.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/RatedArtist.hpp"
#include "database/objects/RatedRelease.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackList.hpp"
#include "database/objects/User.hpp"
#include "services/mumaoutbox/IMumaOutboxRelay.hpp"

namespace lms::feedback::musicManagement
{
    MusicManagementBackend::MusicManagementBackend(db::IDb& db, mumaOutbox::IMumaOutboxRelay* relay)
        : _db{ db }
        , _relay{ relay }
    {
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
                std::string username;
                if (auto user = db::User::find(session, ratedArtist->getUserId()))
                    username = user->getLoginName();

                LMS_LOG(SCROBBLING, INFO, "Rating changed for artist " << artistName << " (rating: " << rating << ", user: " << username << ")");
                sendEvent("rating_changed", mumaOutbox::RatingKey{ .username = username, .objectType = "artist", .objectId = artistName }, rating);
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
                std::string username;
                if (auto user = db::User::find(session, ratedRelease->getUserId()))
                    username = user->getLoginName();

                LMS_LOG(SCROBBLING, INFO, "Rating changed for release " << releaseName << " (rating: " << rating << ", user: " << username << ")");
                sendEvent("rating_changed", mumaOutbox::RatingKey{ .username = username, .objectType = "release", .objectId = releaseName }, rating);
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
                std::string username;
                if (auto user = db::User::find(session, ratedTrack->getUserId()))
                    username = user->getLoginName();

                LMS_LOG(SCROBBLING, INFO, "Rating changed for track " << trackId << " (rating: " << rating << ", path: " << path << ", user: " << username << ")");
                sendEvent("rating_changed", mumaOutbox::RatingKey{ .username = username, .objectType = "track", .objectId = trackId }, rating, path);
            }
        }
    }

    void MusicManagementBackend::onRatingRemoved(const RatingRemovedEvent& event)
    {
        // MuMa's rating mirror is only ever written from here (the sync is one-way), so a
        // cleared rating that is not reported keeps its old star there forever.
        LMS_LOG(SCROBBLING, INFO, "Rating removed for " << event.objectType << " " << event.objectId << " (previous rating: " << event.previousRating << ", user: " << event.username << ")");
        sendEvent("rating_removed", mumaOutbox::RatingKey{ .username = event.username, .objectType = event.objectType, .objectId = event.objectId }, 0, event.path);
    }

    void MusicManagementBackend::onPlaylistChanged(db::TrackListId playlistId)
    {
        (void)playlistId;
    }

    void MusicManagementBackend::sendEvent(std::string_view eventType, const mumaOutbox::RatingKey& key, int rating, const std::string& path)
    {
        if (!_relay)
            return;

        Wt::Json::Object obj;
        obj["event"] = Wt::Json::Value(std::string{ eventType });
        obj["object_type"] = Wt::Json::Value(key.objectType);
        obj["object_id"] = Wt::Json::Value(key.objectId);
        obj["username"] = Wt::Json::Value(key.username);
        obj["rating"] = Wt::Json::Value(rating);
        if (!path.empty())
            obj["path"] = Wt::Json::Value(path);

        // Written to the outbox before anything is sent, on this thread, and delivered from the
        // io_context. The body is fixed here, so every retry sends the same state; the API key is
        // added at send time.
        _relay->enqueueRating(key, Wt::Json::serialize(obj));
    }
} // namespace lms::feedback::musicManagement
