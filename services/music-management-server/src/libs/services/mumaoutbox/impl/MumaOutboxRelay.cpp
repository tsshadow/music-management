/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "MumaOutboxRelay.hpp"

#include <algorithm>
#include <cassert>
#include <optional>
#include <vector>

#include <boost/asio/bind_executor.hpp>
#include <boost/asio/post.hpp>

#include <Wt/Http/Message.h>
#include <Wt/WDateTime.h>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "database/IDb.hpp"
#include "database/MumaListenOutbox.hpp"
#include "database/MumaRatingOutbox.hpp"
#include "database/Session.hpp"

namespace lms::mumaOutbox
{
    namespace
    {
        // music-manager has the row. It answers 200 for a listen it already had (the relay sends
        // the listen's own start time, and (username, listened_at, track) is unique there) and for
        // a rating it already had (an upsert, or a DELETE by key). 409 is accepted too, as the
        // other way a server can say "already have it".
        constexpr int httpOkFirst{ 200 };
        constexpr int httpOkEnd{ 300 };
        constexpr int httpBadRequest{ 400 };
        constexpr int httpConflict{ 409 };
        constexpr int httpPayloadTooLarge{ 413 };
        constexpr int httpUnprocessable{ 422 };

        // music-manager's routes, relative to music-management-url (which already ends in /api).
        constexpr std::string_view listenUrl{ "/scrobble/event" };
        constexpr std::string_view ratingUrl{ "/rating/lms-event" };

        // What repairs a rating the outbox had to give up on: nothing else sends it again.
        constexpr std::string_view ratingRepairHint{ "scripts/restore_lms_ratings.py export-lms and import-muma repair it" };

        bool isDelivered(int status)
        {
            return (status >= httpOkFirst && status < httpOkEnd) || status == httpConflict;
        }

        // music-manager read the row and will never take it: the body itself is wrong. Sending it
        // again cannot help, and keeping it would hold up every row behind it. Everything else --
        // 401/403 after a key rotation, 404 from a proxy mid-deploy, 5xx, 429 -- is a state of
        // the server that passes, so the row waits.
        bool isRefusedForGood(int status)
        {
            return status == httpBadRequest || status == httpPayloadTooLarge || status == httpUnprocessable;
        }

        std::chrono::milliseconds retryDelay(const MumaOutboxSettings& settings, std::size_t consecutiveFailures)
        {
            std::chrono::milliseconds delay{ settings.minRetryDelay };
            for (std::size_t i{ 1 }; i < consecutiveFailures && delay < settings.maxRetryDelay; ++i)
                delay *= 2;
            return std::min(delay, settings.maxRetryDelay);
        }

        std::string describe(const RatingKey& key)
        {
            return "rating of " + key.objectType + " '" + key.objectId + "' by " + key.username;
        }

        std::string toLogTime(const Wt::WDateTime& time)
        {
            return time.toString("yyyy-MM-dd HH:mm:ss").toUTF8();
        }

        long long maxAgeHours(std::chrono::seconds maxAge)
        {
            return std::chrono::duration_cast<std::chrono::hours>(maxAge).count();
        }

        Wt::WDateTime cutoffFor(std::chrono::seconds maxAge)
        {
            return Wt::WDateTime::currentDateTime().addSecs(-static_cast<int>(maxAge.count()));
        }

        // Owns the shared relay for its single owner (core::Service in production, a test), and
        // stops it when let go of, so the relay's callbacks can still find out it is gone.
        class RelayHandle final : public IMumaOutboxRelay
        {
        public:
            explicit RelayHandle(std::shared_ptr<MumaOutboxRelay> relay)
                : _relay{ std::move(relay) }
            {
            }
            ~RelayHandle() override { _relay->stop(); }

            RelayHandle(const RelayHandle&) = delete;
            RelayHandle& operator=(const RelayHandle&) = delete;

            void start() override { _relay->start(); }
            void enqueueListen(std::string_view payload) override { _relay->enqueueListen(payload); }
            void enqueueRating(const RatingKey& key, std::string_view payload) override { _relay->enqueueRating(key, payload); }
            void stop() override { _relay->stop(); }

        private:
            const std::shared_ptr<MumaOutboxRelay> _relay;
        };
    } // namespace

    std::unique_ptr<IMumaOutboxRelay> createMumaOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db)
    {
        auto* config{ core::Service<core::IConfig>::get() };
        // NOTE: "music-management-url" already includes the "/api" prefix (see
        // UserSynchronizer.cpp / MusicManagementPasswordService.cpp); each request appends its
        // own route to it.
        const std::string baseUrl{ config->getString("music-management-url", "") };
        if (baseUrl.empty())
        {
            LMS_LOG(SCROBBLING, INFO, "[MuMa outbox] No music-management-url configured: listens and ratings are not relayed to music-manager");
            return nullptr;
        }

        LMS_LOG(SCROBBLING, INFO, "[MuMa outbox] Relaying listens and ratings to " << baseUrl);
        return createMumaOutboxRelay(ioContext, db, core::http::createClient(ioContext, baseUrl), std::string{ config->getString("music-management-api-key", "") });
    }

    std::unique_ptr<IMumaOutboxRelay> createMumaOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey, MumaOutboxSettings settings)
    {
        return std::make_unique<RelayHandle>(std::make_shared<MumaOutboxRelay>(ioContext, db, std::move(client), std::move(apiKey), settings));
    }

    MumaOutboxRelay::MumaOutboxRelay(boost::asio::io_context& ioContext, db::IDb& db, std::unique_ptr<core::http::IClient> client, std::string apiKey, MumaOutboxSettings settings)
        : _ioContext{ ioContext }
        , _db{ db }
        , _apiKey{ std::move(apiKey) }
        , _settings{ settings }
        , _client{ std::move(client) }
    {
    }

    MumaOutboxRelay::~MumaOutboxRelay() = default;

    void MumaOutboxRelay::start()
    {
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createReadTransaction() };
            const db::mumaListenOutbox::Status listens{ db::mumaListenOutbox::getStatus(session) };
            const db::mumaRatingOutbox::Status ratings{ db::mumaRatingOutbox::getStatus(session) };

            std::optional<Wt::WDateTime> oldest{ listens.oldest };
            if (ratings.oldest && (!oldest || *ratings.oldest < *oldest))
                oldest = ratings.oldest;
            if (oldest)
                LMS_LOG(SCROBBLING, INFO, "[MuMa outbox] Resuming " << listens.count << " listen(s) and " << ratings.count << " rating(s) queued since " << toLogTime(*oldest) << " UTC");
        }
        catch (const std::exception& e)
        {
            // Not a reason to keep LMS from starting; sendNext() reports and retries on its own.
            LMS_LOG(SCROBBLING, ERROR, "[MuMa outbox] Cannot read the outbox: " << e.what());
        }
        wake();
    }

    void MumaOutboxRelay::enqueueListen(std::string_view payload)
    {
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };
            db::mumaListenOutbox::push(session, payload, Wt::WDateTime::currentDateTime());
            if (const std::size_t dropped{ db::mumaListenOutbox::dropOverflow(session, _settings.listenMaxCount) }; dropped > 0)
                LMS_LOG(SCROBBLING, WARNING, "[MuMa outbox] Listen outbox full (" << _settings.listenMaxCount << " listens): dropped the " << dropped << " oldest, music-manager will not get them from here");
        }
        catch (const std::exception& e)
        {
            // LMS's own listen table still has it, and music-manager's backfill reads that.
            LMS_LOG(SCROBBLING, ERROR, "[MuMa outbox] Cannot queue a listen for music-manager: " << e.what());
            return;
        }
        wake();
    }

    void MumaOutboxRelay::enqueueRating(const RatingKey& key, std::string_view payload)
    {
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };
            db::mumaRatingOutbox::replace(session, key, payload, Wt::WDateTime::currentDateTime());
            for (const RatingKey& dropped : db::mumaRatingOutbox::dropOverflow(session, _settings.ratingMaxCount))
                LMS_LOG(SCROBBLING, WARNING, "[MuMa outbox] Rating outbox full (" << _settings.ratingMaxCount << " ratings): dropped the " << describe(dropped) << ", music-manager will not get it; " << ratingRepairHint);
        }
        catch (const std::exception& e)
        {
            LMS_LOG(SCROBBLING, ERROR, "[MuMa outbox] Cannot queue the " << describe(key) << " for music-manager, it is lost: " << e.what());
            return;
        }
        wake();
    }

    void MumaOutboxRelay::stop()
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

    void MumaOutboxRelay::wake()
    {
        boost::asio::post(boost::asio::bind_executor(_strand, [weak = weak_from_this()] {
            if (const auto self{ weak.lock() })
                self->sendNext();
        }));
    }

    void MumaOutboxRelay::sendNext()
    {
        assert(_strand.running_in_this_thread());

        if (_inFlight || _retryPending)
            return;

        std::optional<Pending> pending;
        try
        {
            dropExpired();
            pending = pickNext();
        }
        catch (const std::exception& e)
        {
            LMS_LOG(SCROBBLING, ERROR, "[MuMa outbox] Cannot read the outbox: " << e.what());
            retryLater(std::nullopt);
            return;
        }

        if (pending)
            send(*pending);
    }

    void MumaOutboxRelay::dropExpired()
    {
        db::Session& session{ _db.getTLSSession() };
        const Wt::WDateTime listenCutoff{ cutoffFor(_settings.listenMaxAge) };
        const Wt::WDateTime ratingCutoff{ cutoffFor(_settings.ratingMaxAge) };

        bool listensExpired{};
        bool ratingsExpired{};
        {
            auto transaction{ session.createReadTransaction() };
            const db::mumaListenOutbox::Status listens{ db::mumaListenOutbox::getStatus(session) };
            const db::mumaRatingOutbox::Status ratings{ db::mumaRatingOutbox::getStatus(session) };
            listensExpired = listens.oldest && *listens.oldest < listenCutoff;
            ratingsExpired = ratings.oldest && *ratings.oldest < ratingCutoff;
        }
        if (!listensExpired && !ratingsExpired)
            return;

        auto transaction{ session.createWriteTransaction() };
        if (listensExpired)
        {
            const std::size_t dropped{ db::mumaListenOutbox::dropOlderThan(session, listenCutoff) };
            LMS_LOG(SCROBBLING, WARNING, "[MuMa outbox] Dropped " << dropped << " listen(s) music-manager did not take within " << maxAgeHours(_settings.listenMaxAge) << " hours");
        }
        if (ratingsExpired)
        {
            for (const RatingKey& dropped : db::mumaRatingOutbox::dropOlderThan(session, ratingCutoff))
                LMS_LOG(SCROBBLING, WARNING, "[MuMa outbox] Dropped the " << describe(dropped) << ": music-manager did not take it within " << maxAgeHours(_settings.ratingMaxAge) << " hours; " << ratingRepairHint);
        }
    }

    std::optional<MumaOutboxRelay::Pending> MumaOutboxRelay::pickNext()
    {
        db::Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };
        std::optional<db::mumaListenOutbox::Entry> listen{ db::mumaListenOutbox::front(session) };
        std::optional<db::mumaRatingOutbox::Entry> rating{ db::mumaRatingOutbox::front(session) };

        // Oldest first across both tables; on a tie the listen goes first. music-manager treats
        // the two independently, so the order between them only decides who waits.
        if (listen && (!rating || listen->created <= rating->created))
            return Pending{ .table = Table::Listen, .id = listen->id, .payload = std::move(listen->payload), .label = "listen" };
        if (rating)
            return Pending{ .table = Table::Rating, .id = rating->id, .payload = std::move(rating->payload), .label = describe(rating->key) };
        return std::nullopt;
    }

    void MumaOutboxRelay::send(const Pending& pending)
    {
        core::http::ClientPOSTRequestParameters request;
        request.relativeUrl = std::string{ pending.table == Table::Listen ? listenUrl : ratingUrl };
        // Any answer is handed back as it is, so this class decides per status what happens to
        // the row; only a transport error arrives as a failure.
        request.treatAnyStatusAsSuccess = true;
        request.message.addHeader("Content-Type", "application/json");
        if (!_apiKey.empty())
            request.message.addHeader("X-API-Key", _apiKey);
        request.message.addBodyText(pending.payload);

        const Kept row{ .table = pending.table, .id = pending.id };
        const std::weak_ptr<MumaOutboxRelay> weak{ weak_from_this() };
        request.onSuccessFunc = [weak, row](const Wt::Http::Message& msg) {
            const int status{ msg.status() };
            if (const auto self{ weak.lock() })
                boost::asio::post(boost::asio::bind_executor(self->_strand, [self, answer = Answer{ .table = row.table, .id = row.id, .status = status }] { self->onAnswer(answer); }));
        };
        request.onFailureFunc = [weak, row] {
            if (const auto self{ weak.lock() })
                boost::asio::post(boost::asio::bind_executor(self->_strand, [self, row] { self->onTransportFailure(row); }));
        };
        request.onAbortFunc = [weak] {
            // Only stop() aborts; the row stays in its outbox for the next start.
            if (const auto self{ weak.lock() })
                boost::asio::post(boost::asio::bind_executor(self->_strand, [self] { self->_inFlight = false; }));
        };

        const std::scoped_lock lock{ _clientMutex };
        if (_stopped || !_client)
            return;
        _inFlight = true;
        _inFlightLabel = pending.label;
        _client->sendPOSTRequest(std::move(request));
    }

    void MumaOutboxRelay::onAnswer(const Answer& answer)
    {
        assert(_strand.running_in_this_thread());
        const int status{ answer.status };
        _inFlight = false;

        if (!isDelivered(status) && !isRefusedForGood(status))
        {
            LMS_LOG(SCROBBLING, DEBUG, "[MuMa outbox] music-manager answered HTTP " << status << " to the " << _inFlightLabel << ", keeping it");
            retryLater(Kept{ .table = answer.table, .id = answer.id });
            return;
        }

        if (!isDelivered(status) && answer.table == Table::Rating)
            LMS_LOG(SCROBBLING, WARNING, "[MuMa outbox] music-manager refused the " << _inFlightLabel << " for good (HTTP " << status << "), dropped it; " << ratingRepairHint);
        else if (!isDelivered(status))
            LMS_LOG(SCROBBLING, WARNING, "[MuMa outbox] music-manager refused a listen for good (HTTP " << status << "), dropped it");
        else if (_consecutiveFailures > 0)
            LMS_LOG(SCROBBLING, INFO, "[MuMa outbox] music-manager takes listens and ratings again after " << _consecutiveFailures << " failed attempt(s)");

        _consecutiveFailures = 0;
        if (!remove(answer.table, answer.id))
        {
            // Sending on would send the same row straight away, and again, as fast as
            // music-manager answers. Harmless there, but not a loop to run.
            retryLater(std::nullopt);
            return;
        }
        sendNext();
    }

    void MumaOutboxRelay::onTransportFailure(const Kept& kept)
    {
        assert(_strand.running_in_this_thread());
        _inFlight = false;

        retryLater(kept);
    }

    void MumaOutboxRelay::retryLater(std::optional<Kept> kept)
    {
        assert(_strand.running_in_this_thread());

        ++_consecutiveFailures;
        std::size_t listens{};
        std::size_t ratings{};
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };
            if (kept && kept->table == Table::Listen)
                db::mumaListenOutbox::recordAttempt(session, kept->id);
            else if (kept)
                db::mumaRatingOutbox::recordAttempt(session, kept->id);
            listens = db::mumaListenOutbox::getStatus(session).count;
            ratings = db::mumaRatingOutbox::getStatus(session).count;
        }
        catch (const std::exception& e)
        {
            LMS_LOG(SCROBBLING, ERROR, "[MuMa outbox] Cannot record a failed delivery: " << e.what());
        }

        const std::chrono::milliseconds delay{ retryDelay(_settings, _consecutiveFailures) };
        // Once per outage, not once per attempt: an outage of an hour is sixty attempts.
        if (_consecutiveFailures == 1)
            LMS_LOG(SCROBBLING, WARNING, "[MuMa outbox] Delivery to music-manager failed, keeping " << listens << " listen(s) and " << ratings << " rating(s) in the outbox and retrying");
        LMS_LOG(SCROBBLING, DEBUG, "[MuMa outbox] Retry " << _consecutiveFailures << " in " << delay.count() << " ms");

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

    bool MumaOutboxRelay::remove(Table table, long long id)
    {
        try
        {
            db::Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };
            if (table == Table::Listen)
                db::mumaListenOutbox::remove(session, id);
            else
                db::mumaRatingOutbox::remove(session, id);
            return true;
        }
        catch (const std::exception& e)
        {
            // It is sent again later; music-manager takes a repeat as a no-op.
            LMS_LOG(SCROBBLING, ERROR, "[MuMa outbox] Cannot remove a delivered row from the outbox: " << e.what());
            return false;
        }
    }
} // namespace lms::mumaOutbox
