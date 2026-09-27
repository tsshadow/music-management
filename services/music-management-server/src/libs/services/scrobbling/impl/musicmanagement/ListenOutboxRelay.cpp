/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "ListenOutboxRelay.hpp"

#include <algorithm>
#include <cassert>
#include <optional>

#include <boost/asio/bind_executor.hpp>
#include <boost/asio/post.hpp>

#include <Wt/Http/Message.h>
#include <Wt/WDateTime.h>

#include "core/ILogger.hpp"
#include "database/IDb.hpp"
#include "database/MumaListenOutbox.hpp"
#include "database/Session.hpp"

#define LOG(sev, message) LMS_LOG(SCROBBLING, sev, "[MuMa listen outbox] " << message)

namespace lms::scrobbling::musicManagement
{
    namespace
    {
        // music-manager has the listen. It answers 200 for a listen it already had as well: the
        // relay sends the listen's own start time, and (username, listened_at, track) is unique
        // there. 409 is accepted too, as the other way a server can say "already have it".
        bool isDelivered(int status)
        {
            return (status >= 200 && status < 300) || status == 409;
        }

        // music-manager read the listen and will never take it: the body itself is wrong. Sending
        // it again cannot help, and keeping it would hold up every listen behind it. Everything
        // else -- 401/403 after a key rotation, 404 from a proxy mid-deploy, 5xx, 429 -- is a
        // state of the server that passes, so the listen waits.
        bool isRefusedForGood(int status)
        {
            return status == 400 || status == 413 || status == 422;
        }

        std::chrono::milliseconds retryDelay(const ListenOutboxSettings& settings, std::size_t consecutiveFailures)
        {
            std::chrono::milliseconds delay{ settings.minRetryDelay };
            for (std::size_t i{ 1 }; i < consecutiveFailures && delay < settings.maxRetryDelay; ++i)
                delay *= 2;
            return std::min(delay, settings.maxRetryDelay);
        }
    } // namespace

    ListenOutboxRelay::ListenOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey, ListenOutboxSettings settings)
        : _ioContext{ ioContext }
        , _db{ db }
        , _apiKey{ std::move(apiKey) }
        , _settings{ settings }
        , _client{ std::move(client) }
    {
    }

    ListenOutboxRelay::~ListenOutboxRelay() = default;

    void ListenOutboxRelay::start()
    {
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createReadTransaction() };
            const db::mumaListenOutbox::Status status{ db::mumaListenOutbox::getStatus(session) };
            if (status.count > 0)
                LOG(INFO, "Resuming " << status.count << " listen(s) queued since " << status.oldest->toString("yyyy-MM-dd HH:mm:ss").toUTF8() << " UTC");
        }
        catch (const std::exception& e)
        {
            // Not a reason to keep LMS from starting; sendNext() reports and retries on its own.
            LOG(ERROR, "Cannot read the outbox: " << e.what());
        }
        wake();
    }

    void ListenOutboxRelay::enqueue(std::string_view payload)
    {
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };
            db::mumaListenOutbox::push(session, payload, Wt::WDateTime::currentDateTime());
            if (const std::size_t dropped{ db::mumaListenOutbox::dropOverflow(session, _settings.maxCount) }; dropped > 0)
                LOG(WARNING, "Outbox full (" << _settings.maxCount << " listens): dropped the " << dropped << " oldest, music-manager will not get them from here");
        }
        catch (const std::exception& e)
        {
            // LMS's own listen table still has it, and music-manager's backfill reads that.
            LOG(ERROR, "Cannot queue a listen for music-manager: " << e.what());
            return;
        }
        wake();
    }

    void ListenOutboxRelay::stop()
    {
        std::unique_ptr<core::http::IClient> client;
        {
            const std::scoped_lock lock{ _clientMutex };
            _stopped = true;
            client = std::move(_client);
        }
        // Outside the lock: destroying the client aborts its queue and waits for it, and the
        // abort callbacks only post to the strand.
        client.reset();
    }

    void ListenOutboxRelay::wake()
    {
        boost::asio::post(boost::asio::bind_executor(_strand, [weak = weak_from_this()] {
            if (const auto self{ weak.lock() })
                self->sendNext();
        }));
    }

    void ListenOutboxRelay::sendNext()
    {
        assert(_strand.running_in_this_thread());

        if (_inFlight || _retryPending)
            return;

        std::optional<db::mumaListenOutbox::Entry> entry;
        try
        {
            db::Session& session{ _db.getTLSSession() };
            const Wt::WDateTime cutoff{ Wt::WDateTime::currentDateTime().addSecs(-static_cast<int>(_settings.maxAge.count())) };

            bool hasExpired{};
            {
                auto transaction{ session.createReadTransaction() };
                const db::mumaListenOutbox::Status status{ db::mumaListenOutbox::getStatus(session) };
                hasExpired = status.oldest && *status.oldest < cutoff;
                if (!hasExpired)
                    entry = db::mumaListenOutbox::front(session);
            }
            if (hasExpired)
            {
                auto transaction{ session.createWriteTransaction() };
                const std::size_t dropped{ db::mumaListenOutbox::dropOlderThan(session, cutoff) };
                LOG(WARNING, "Dropped " << dropped << " listen(s) music-manager did not take within " << std::chrono::duration_cast<std::chrono::hours>(_settings.maxAge).count() << " hours");
                entry = db::mumaListenOutbox::front(session);
            }
        }
        catch (const std::exception& e)
        {
            LOG(ERROR, "Cannot read the outbox: " << e.what());
            retryLater(std::nullopt);
            return;
        }

        if (!entry)
            return;

        core::http::ClientPOSTRequestParameters request;
        // Any answer is handed back as it is, so this class decides per status what happens to
        // the listen; only a transport error arrives as a failure.
        request.treatAnyStatusAsSuccess = true;
        request.message.addHeader("Content-Type", "application/json");
        if (!_apiKey.empty())
            request.message.addHeader("X-API-Key", _apiKey);
        request.message.addBodyText(entry->payload);

        const long long id{ entry->id };
        const std::weak_ptr<ListenOutboxRelay> weak{ weak_from_this() };
        request.onSuccessFunc = [weak, id](const Wt::Http::Message& msg) {
            const int status{ msg.status() };
            if (const auto self{ weak.lock() })
                boost::asio::post(boost::asio::bind_executor(self->_strand, [self, id, status] { self->onAnswer(id, status); }));
        };
        request.onFailureFunc = [weak, id] {
            if (const auto self{ weak.lock() })
                boost::asio::post(boost::asio::bind_executor(self->_strand, [self, id] { self->onTransportFailure(id); }));
        };
        request.onAbortFunc = [weak] {
            // Only stop() aborts; the listen stays in the outbox for the next start.
            if (const auto self{ weak.lock() })
                boost::asio::post(boost::asio::bind_executor(self->_strand, [self] { self->_inFlight = false; }));
        };

        const std::scoped_lock lock{ _clientMutex };
        if (_stopped || !_client)
            return;
        _inFlight = true;
        _client->sendPOSTRequest(std::move(request));
    }

    void ListenOutboxRelay::onAnswer(long long id, int status)
    {
        assert(_strand.running_in_this_thread());
        _inFlight = false;

        if (isDelivered(status) || isRefusedForGood(status))
        {
            if (!isDelivered(status))
                LOG(WARNING, "music-manager refused a listen for good (HTTP " << status << "), dropped it");
            else if (_consecutiveFailures > 0)
                LOG(INFO, "music-manager takes listens again after " << _consecutiveFailures << " failed attempt(s)");

            _consecutiveFailures = 0;
            if (!remove(id))
            {
                // Sending on would send the same listen straight away, and again, as fast as
                // music-manager answers. Harmless there, but not a loop to run.
                retryLater(std::nullopt);
                return;
            }
            sendNext();
            return;
        }

        LOG(DEBUG, "music-manager answered HTTP " << status << ", keeping the listen");
        retryLater(id);
    }

    void ListenOutboxRelay::onTransportFailure(long long id)
    {
        assert(_strand.running_in_this_thread());
        _inFlight = false;

        retryLater(id);
    }

    void ListenOutboxRelay::retryLater(std::optional<long long> id)
    {
        assert(_strand.running_in_this_thread());

        ++_consecutiveFailures;
        std::size_t waiting{};
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };
            if (id)
                db::mumaListenOutbox::recordAttempt(session, *id);
            waiting = db::mumaListenOutbox::getStatus(session).count;
        }
        catch (const std::exception& e)
        {
            LOG(ERROR, "Cannot record a failed delivery: " << e.what());
        }

        const std::chrono::milliseconds delay{ retryDelay(_settings, _consecutiveFailures) };
        // Once per outage, not once per attempt: an outage of an hour is sixty attempts.
        if (_consecutiveFailures == 1)
            LOG(WARNING, "music-manager did not take a listen, keeping " << waiting << " listen(s) in the outbox and retrying");
        LOG(DEBUG, "Retry " << _consecutiveFailures << " in " << delay.count() << " ms");

        _retryPending = true;
        _retryTimer.expires_after(delay);
        _retryTimer.async_wait(boost::asio::bind_executor(_strand, [weak = weak_from_this()](const boost::system::error_code& ec) {
            const auto self{ weak.lock() };
            if (!self || ec)
                return;
            self->_retryPending = false;
            self->sendNext();
        }));
    }

    bool ListenOutboxRelay::remove(long long id)
    {
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };
            db::mumaListenOutbox::remove(session, id);
            return true;
        }
        catch (const std::exception& e)
        {
            // It is sent again later; music-manager deduplicates it on its start time.
            LOG(ERROR, "Cannot remove a delivered listen from the outbox: " << e.what());
            return false;
        }
    }
} // namespace lms::scrobbling::musicManagement
