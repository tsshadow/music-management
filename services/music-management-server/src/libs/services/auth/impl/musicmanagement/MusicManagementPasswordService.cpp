/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#include "MusicManagementPasswordService.hpp"

#include <optional>

#include <Wt/Http/Client.h>
#include <Wt/Http/Message.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Value.h>
#include <boost/asio/steady_timer.hpp>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"

namespace lms::auth::musicManagement
{
    PasswordCheckOutcome outcomeFromResponseStatus(int status)
    {
        switch (status)
        {
        case 200:
            return PasswordCheckOutcome::Match;
        case 401:
        case 403:
            return PasswordCheckOutcome::Mismatch;
        case 429:
            return PasswordCheckOutcome::Throttled;
        default:
            return PasswordCheckOutcome::BackendError;
        }
    }

    Wt::Http::Message buildLoginRequest(const LoginRequestFields& fields)
    {
        Wt::Http::Message message;
        message.addHeader("Content-Type", "application/json");
        if (!fields.apiKey.empty())
            message.addHeader("X-API-Key", std::string{ fields.apiKey });
        if (!fields.clientAddress.is_unspecified())
            message.addHeader("X-Forwarded-For", fields.clientAddress.to_string());

        Wt::Json::Object body;
        body["username"] = Wt::Json::Value(std::string{ fields.loginName });
        body["password"] = Wt::Json::Value(std::string{ fields.password });
        message.addBodyText(Wt::Json::serialize(body));
        return message;
    }

    MusicManagementPasswordService::MusicManagementPasswordService(boost::asio::io_context& /*ioContext*/, db::IDb& db, std::size_t maxThrottlerEntryCount)
        // music-manager rate limits per account on its own side, so LMS must not also throttle:
        // its throttler keys on the client address, which for Subsonic requests is the internal
        // reverse-proxy hop that every user shares.
        : PasswordServiceBase{ db, maxThrottlerEntryCount, /*useLoginThrottler*/ false }
    {
        _apiUrl = std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") } + "/auth/login";
        _apiKey = std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") };
        _timeout = std::chrono::milliseconds{ core::Service<core::IConfig>::get()->getULong("music-management-auth-timeout-ms", 2000) };

        LMS_LOG(AUTH, INFO, "MusicManagementPasswordService: Using API URL: " << _apiUrl << ", timeout: " << _timeout.count() << "ms");
    }

    MusicManagementPasswordService::~MusicManagementPasswordService() = default;

    PasswordCheckOutcome MusicManagementPasswordService::checkUserPassword(std::string_view loginName, std::string_view password)
    {
        return checkUserPasswordFrom(boost::asio::ip::address{}, loginName, password);
    }

    PasswordCheckOutcome MusicManagementPasswordService::checkUserPasswordFrom(const boost::asio::ip::address& clientAddress, std::string_view loginName, std::string_view password)
    {
        if (_apiUrl.empty())
        {
            LMS_LOG(AUTH, ERROR, "MusicManagement authentication: no music-management-url configured");
            return PasswordCheckOutcome::BackendError;
        }

        // Deliberately a private io_context and a private client per call, instead of the shared
        // core::http::IClient. That client is built for polite outbound calls to third-party APIs:
        // it serializes every request through one SendQueue, retries on error, and parks the whole
        // queue for 30s when anything fails. On an auth check that is ruinous - a single connection
        // error after music-manager is redeployed stops all authentication for 30s, every waiting
        // caller times out and is reported as a wrong password, and the clients' retries keep the
        // queue full so it never recovers. Password checks are independent of each other and are on
        // the request path; they must not queue behind one another or share failure state.
        //
        // Running the io_context inline also bounds the lifetime of everything the callback touches:
        // run() only returns once the client is done, so the locals below cannot be written to after
        // this frame is gone.
        boost::asio::io_context ioContext;

        Wt::Http::Client client{ ioContext };
        client.setTimeout(_timeout);
        client.setFollowRedirect(false);
        client.setMaximumResponseSize(64 * 1024);

        // Wt's own timeout should always fire, but a client that never completes would otherwise
        // hang this thread forever. This deadline is the backstop, not the normal path; it is
        // cancelled as soon as the request finishes, so a fast answer returns immediately rather
        // than waiting for the timer to expire.
        boost::asio::steady_timer deadline{ ioContext };

        std::optional<PasswordCheckOutcome> outcome;
        client.done().connect([&](Wt::AsioWrapper::error_code ec, const Wt::Http::Message& msg) {
            deadline.cancel();

            if (ec)
            {
                LMS_LOG(AUTH, ERROR, "MusicManagement authentication: cannot reach " << _apiUrl << ": " << ec.message());
                outcome = PasswordCheckOutcome::BackendError;
                return;
            }

            outcome = outcomeFromResponseStatus(msg.status());
            if (*outcome == PasswordCheckOutcome::BackendError)
                LMS_LOG(AUTH, ERROR, "MusicManagement authentication: unexpected status " << msg.status() << " from " << _apiUrl);
            else if (*outcome == PasswordCheckOutcome::Throttled)
                LMS_LOG(AUTH, WARNING, "MusicManagement authentication: rate limited for user '" << loginName << "'");
        });

        const Wt::Http::Message message{ buildLoginRequest({ .loginName = loginName, .password = password, .apiKey = _apiKey, .clientAddress = clientAddress }) };

        if (!client.post(_apiUrl, message))
        {
            LMS_LOG(AUTH, ERROR, "MusicManagement authentication: bad url '" << _apiUrl << "'");
            return PasswordCheckOutcome::BackendError;
        }

        deadline.expires_after(_timeout + std::chrono::seconds{ 1 });
        deadline.async_wait([&](const boost::system::error_code& ec) {
            if (ec)
                return; // cancelled: the request finished first

            LMS_LOG(AUTH, ERROR, "MusicManagement authentication: no answer within deadline, aborting");
            client.abort();
            ioContext.stop();
        });

        ioContext.run();

        if (!outcome)
        {
            LMS_LOG(AUTH, ERROR, "MusicManagement authentication timed out for user '" << loginName << "'");
            return PasswordCheckOutcome::BackendError;
        }

        return *outcome;
    }

    IPasswordService::PasswordAcceptabilityResult MusicManagementPasswordService::checkPasswordAcceptability(std::string_view /*password*/, const PasswordValidationContext& /*context*/) const
    {
        return PasswordAcceptabilityResult::OK;
    }

    void MusicManagementPasswordService::setPassword(db::UserId /*userId*/, std::string_view /*newPassword*/)
    {
        // Not supported
    }
} // namespace lms::auth::musicManagement
