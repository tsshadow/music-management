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
        , _apiUrl{ core::Service<core::IConfig>::get()->getString("music-management-scrobbling-api-url", "") }
        , _apiKey{ core::Service<core::IConfig>::get()->getString("music-management-scrobbling-api-key", "") }
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
        payload["user"] = Wt::Json::Value(std::string{ user->getLoginName() });
        payload["source"] = Wt::Json::Value("lms");
        
        Wt::WDateTime listenedAt = timePoint.isValid() ? timePoint : Wt::WDateTime::currentDateTime();
        payload["listened_at"] = Wt::Json::Value(listenedAt.toString("yyyy-MM-ddTHH:mm:ss.000Z").toUTF8());
        
        if (duration)
            payload["duration_secs"] = Wt::Json::Value(static_cast<long long>(duration->count()));
        
        payload["source_track_id"] = Wt::Json::Value(track->getId().toString());

        Wt::Json::Object trackInput;
        trackInput["title"] = Wt::Json::Value(std::string{ track->getName() });
        if (auto release = track->getRelease())
        {
            trackInput["album"] = Wt::Json::Value(std::string{ release->getName() });
            auto date = release->getOriginalDate();
            if (date.isValid())
            {
                if (auto year = date.getYear())
                    trackInput["album_year"] = Wt::Json::Value(static_cast<long long>(*year));
            }
        }
        
        if (auto trackNo = track->getTrackNumber())
            trackInput["track_no"] = Wt::Json::Value(static_cast<long long>(*trackNo));
        
        if (auto medium = track->getMedium())
        {
            if (auto pos = medium->getPosition())
                trackInput["disc_no"] = Wt::Json::Value(static_cast<long long>(*pos));
        }
            
        trackInput["duration_secs"] = Wt::Json::Value(static_cast<long long>(std::chrono::duration_cast<std::chrono::seconds>(track->getDuration()).count()));
        
        if (auto mbid = track->getTrackMBID())
            trackInput["mbid"] = Wt::Json::Value(std::string{ mbid->getAsString() });

        payload["track"] = std::move(trackInput);

        Wt::Json::Array artists;
        for (const auto& link : track->getArtistLinks(db::TrackArtistLinkType::Artist))
        {
            Wt::Json::Object artist;
            artist["name"] = Wt::Json::Value(std::string{ link->getArtistName() });
            artist["role"] = Wt::Json::Value("primary");
            artists.push_back(std::move(artist));
        }
        payload["library_artists"] = std::move(artists);

        core::http::ClientPOSTRequestParameters request;
        request.message.addHeader("Content-Type", "application/json");
        if (!_apiKey.empty())
            request.message.addHeader("X-API-Key", _apiKey);

        std::string jsonBody = Wt::Json::serialize(payload);
        request.message.addBodyText(jsonBody);

        _client->sendPOSTRequest(std::move(request));
    }
} // namespace lms::scrobbling::musicManagement
