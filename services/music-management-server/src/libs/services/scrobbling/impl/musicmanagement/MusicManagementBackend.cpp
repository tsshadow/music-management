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
    namespace
    {
        // NOTE: "music-management-url" already includes the "/api" prefix
        // (see UserSynchronizer.cpp / MusicManagementPasswordService.cpp, which
        // append "/users/" and "/auth/login" directly onto it). The real route
        // is "/api/scrobble/event", so only "/scrobble/event" must be appended here.
        std::unique_ptr<core::http::IClient> createConfiguredClient(boost::asio::io_context& ioContext)
        {
            const std::string apiUrl{ std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") } + "/scrobble/event" };
            LMS_LOG(SCROBBLING, INFO, "MusicManagement scrobbling backend started with API: " << apiUrl);
            return core::http::createClient(ioContext, apiUrl);
        }
    } // namespace

    MusicManagementBackend::MusicManagementBackend(boost::asio::io_context& ioContext, db::IDb& db)
        : MusicManagementBackend{ db, createConfiguredClient(ioContext), std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") } }
    {
    }

    MusicManagementBackend::MusicManagementBackend(db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey)
        : _db{ db }
        , _apiKey{ std::move(apiKey) }
        , _client{ std::move(client) }
    {
    }

    MusicManagementBackend::~MusicManagementBackend() = default;

    void MusicManagementBackend::listenStarted(const Listen& listen)
    {
        // Intentionally not forwarded: music-manager's /scrobble/event has no
        // way to distinguish a "now playing" ping from a real listen (it
        // always records a `listened_at` timestamp, defaulting to "now" when
        // none is given). Forwarding this used to cause every started
        // playback to be counted as a definitive listen, even if skipped
        // immediately. Only listenFinished()/addTimedListen() should report a listen.
        (void)listen;
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

        // Scrobbling to the central MuMa database is on for every user: it is what
        // feeds the shared listening history, so it is not an opt-out.
        const db::User::pointer user{ db::User::find(session, listen.userId) };
        if (!user)
            return;

        const db::Track::pointer track{ db::Track::find(session, listen.trackId) };
        if (!track)
            return;

        Wt::Json::Object payload;
        payload["username"] = Wt::Json::Value(std::string{ user->getLoginName() });

        // Where the play happened, not which server relayed it. Every listen used to claim "lms",
        // which made the web player, the phone and the car indistinguishable afterwards. That
        // value is kept only as the fallback for a caller that did not say.
        payload["source"] = Wt::Json::Value(listen.source.empty() ? std::string{ "lms" } : listen.source);

        // How long the track was actually played. This arrives from the player and used to be
        // discarded here, which left "minutes listened" unanswerable: most of this library is DJ
        // sets, so plays multiplied by track length is not an approximation of it. A duration
        // carried on the listen wins, because it came from the client that did the playing; the
        // argument is what the local player reports for its own playback.
        const std::optional<std::chrono::seconds> playedDuration{ listen.playedDuration ? listen.playedDuration : duration };
        if (playedDuration && playedDuration->count() > 0)
            payload["played_secs"] = Wt::Json::Value(static_cast<long long>(playedDuration->count()));

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
