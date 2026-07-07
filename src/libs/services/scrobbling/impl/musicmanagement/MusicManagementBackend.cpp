/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#include "MusicManagementBackend.hpp"

#include <Wt/Http/Client.h>
#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Value.h>
#include <Wt/WDateTime.h>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/Medium.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackArtistLink.hpp"
#include "database/objects/User.hpp"

namespace lms::scrobbling::musicManagement
{
    MusicManagementBackend::MusicManagementBackend(boost::asio::io_context& ioContext, db::IDb& db)
        : _ioContext{ ioContext }
        , _db{ db }
        , _apiUrl{ std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") } + "/scrobble/api/event" }
        , _apiKey{ std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") } }
    {
        if (!_apiUrl.empty())
        {
            _client = core::http::createClient(_ioContext, _apiUrl);
            LMS_LOG(SCROBBLING, INFO, "MusicManagement scrobbling backend started with API: " << _apiUrl);
        }
    }

    MusicManagementBackend::~MusicManagementBackend() = default;

    void MusicManagementBackend::listenStarted(const Listen& listen)
    {
        sendScrobble(listen, {});
    }

    void MusicManagementBackend::listenFinished(const Listen& listen, std::optional<std::chrono::seconds> duration)
    {
        sendScrobble(listen, Wt::WDateTime::currentDateTime(), duration);
    }

    void MusicManagementBackend::addTimedListen(const TimedListen& listen)
    {
        sendScrobble(listen, listen.listenedAt);
    }

    void MusicManagementBackend::sendScrobble(const Listen& listen, const Wt::WDateTime& timePoint, std::optional<std::chrono::seconds> duration)
    {
        (void)duration;
        if (!_client)
            return;

        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        const db::User::pointer user{ db::User::find(session, listen.userId) };
        if (!user || !user->getMumaScrobblingEnabled())
            return;

        const db::Track::pointer track{ db::Track::find(session, listen.trackId) };
        if (!track)
            return;

        Wt::Json::Object payload;
        payload["username"] = Wt::Json::Value(std::string{ user->getLoginName() });
        payload["source"] = Wt::Json::Value("lms");
        
        Wt::WDateTime listenedAt = timePoint.isValid() ? timePoint : Wt::WDateTime::currentDateTime();
        payload["listened_at"] = Wt::Json::Value(static_cast<long long>(listenedAt.toTime_t()));
        
        payload["track_title"] = Wt::Json::Value(std::string{ track->getName() });
        
        if (auto release = track->getRelease())
        {
            payload["album_name"] = Wt::Json::Value(std::string{ release->getName() });
        }
        
        if (auto mbid = track->getTrackMBID())
            payload["mbid_track"] = Wt::Json::Value(std::string{ mbid->getAsString() });

        for (const auto& link : track->getArtistLinks(db::TrackArtistLinkType::Artist))
        {
            payload["artist_name"] = Wt::Json::Value(std::string{ link->getArtistName() });
            break;
        }

        core::http::ClientPOSTRequestParameters request;
        request.message.addHeader("Content-Type", "application/json");
        if (!_apiKey.empty())
            request.message.addHeader("X-API-Key", _apiKey);

        std::string jsonBody = Wt::Json::serialize(payload);
        request.message.addBodyText(jsonBody);

        _client->sendPOSTRequest(std::move(request));
    }
} // namespace lms::scrobbling::musicManagement
