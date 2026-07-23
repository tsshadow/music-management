/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#include "MusicManagementPasswordService.hpp"

#include <future>
#include <Wt/Http/Message.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Value.h>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "core/http/IClient.hpp"
#include "core/http/ClientRequestParameters.hpp"

namespace lms::auth::musicManagement
{
    MusicManagementPasswordService::MusicManagementPasswordService(boost::asio::io_context& ioContext, db::IDb& db, std::size_t maxThrottlerEntryCount)
        : PasswordServiceBase{ db, maxThrottlerEntryCount }
    {
        _apiUrl = std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") } + "/auth/login";
        _apiKey = std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") };
        
        LMS_LOG(AUTH, INFO, "MusicManagementPasswordService: Using API URL: " << _apiUrl);
        _client = core::http::createClient(ioContext, _apiUrl);
    }

    MusicManagementPasswordService::~MusicManagementPasswordService() = default;

    bool MusicManagementPasswordService::checkUserPassword(std::string_view loginName, std::string_view password)
    {
        if (!_client)
            return false;

        std::promise<bool> promise;
        std::future<bool> future = promise.get_future();

        core::http::ClientPOSTRequestParameters request;
        request.message.addHeader("Content-Type", "application/json");
        if (!_apiKey.empty())
        {
            request.message.addHeader("X-API-Key", _apiKey);
        }

        Wt::Json::Object obj;
        obj["username"] = Wt::Json::Value(std::string{ loginName });
        obj["password"] = Wt::Json::Value(std::string{ password });
        request.message.addBodyText(Wt::Json::serialize(obj));

        request.onSuccessFunc = [&promise](const Wt::Http::Message& msg) {
            if (msg.status() == 200)
            {
                promise.set_value(true);
            }
            else
            {
                LMS_LOG(AUTH, WARNING, "MusicManagement authentication failed for user, status: " << msg.status());
                promise.set_value(false);
            }
        };

        request.onFailureFunc = [&promise]() {
            LMS_LOG(AUTH, ERROR, "MusicManagement authentication failed: connection error");
            promise.set_value(false);
        };

        _client->sendPOSTRequest(std::move(request));

        if (future.wait_for(std::chrono::seconds(10)) == std::future_status::ready)
        {
            return future.get();
        }

        LMS_LOG(AUTH, ERROR, "MusicManagement authentication timed out");
        return false;
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
