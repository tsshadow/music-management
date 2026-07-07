/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#include "UserSynchronizer.hpp"

#include <Wt/Http/Client.h>
#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>
#include <Wt/Json/Value.h>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "core/http/IClient.hpp"
#include "core/http/ClientRequestParameters.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/User.hpp"

namespace lms::auth
{
    std::unique_ptr<IUserSynchronizer> createUserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db)
    {
        return std::make_unique<musicManagement::UserSynchronizer>(ioContext, db);
    }

    namespace musicManagement
    {
        UserSynchronizer::UserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db)
        : _ioContext{ ioContext }
        , _db{ db }
        , _apiUrl{ std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") } + "/users/" }
        , _apiKey{ std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") } }
    {
        LMS_LOG(AUTH, INFO, "Starting MusicManagement user synchronizer... API endpoint = '" << _apiUrl << "'");
        _client = core::http::createClient(_ioContext, _apiUrl);
    }

    UserSynchronizer::~UserSynchronizer()
    {
        LMS_LOG(AUTH, INFO, "Stopped MusicManagement user synchronizer!");
    }

    void UserSynchronizer::syncUsers()
    {
        if (!_client)
            return;

        LMS_LOG(AUTH, INFO, "Syncing users from MusicManagement...");

        core::http::ClientGETRequestParameters request;
        if (!_apiKey.empty())
        {
            request.headers.emplace_back("X-API-Key", _apiKey);
        }

        request.onSuccessFunc = [this](const Wt::Http::Message& msg) {
            if (msg.status() == 200)
            {
                try
                {
                    Wt::Json::Value root;
                    Wt::Json::parse(msg.body(), root);
                    const Wt::Json::Array& usersArray = root;

                    db::Session& session{ _db.getTLSSession() };
                    auto transaction{ session.createWriteTransaction() };

                    for (const auto& userVal : usersArray)
                    {
                        const Wt::Json::Object& userObj = userVal;
                        std::string username = userObj.get("username");
                        int mumaId = static_cast<int>(userObj.get("id"));
                        
                        bool isAdmin = false;
                        const Wt::Json::Value& isAdminVal = userObj.get("is_admin");
                        if (isAdminVal.type() == Wt::Json::Type::Bool)
                            isAdmin = static_cast<bool>(isAdminVal);
                        else if (isAdminVal.type() == Wt::Json::Type::Number)
                            isAdmin = static_cast<double>(isAdminVal) != 0;

                        db::User::pointer user = db::User::findByMumaId(session, mumaId);
                        if (!user)
                            user = db::User::find(session, username);

                        if (user)
                        {
                            LMS_LOG(AUTH, DEBUG, "User '" << user->getLoginName() << "' already exists, updating properties.");
                            user.modify()->setMumaId(mumaId);
                            user.modify()->setLoginName(username);
                            user.modify()->setType(isAdmin ? db::UserType::ADMIN : db::UserType::REGULAR);
                        }
                        else
                        {
                            LMS_LOG(AUTH, INFO, "Creating new user '" << username << "' from MusicManagement.");
                            db::User::pointer newUser{ session.create<db::User>(username) };
                            newUser.modify()->setMumaId(mumaId);
                            newUser.modify()->setType(isAdmin ? db::UserType::ADMIN : db::UserType::REGULAR);
                        }
                    }
                }
                catch (const std::exception& e)
                {
                    LMS_LOG(AUTH, WARNING, "Failed to parse MusicManagement users: " << e.what());
                }
            }
            else
            {
                LMS_LOG(AUTH, WARNING, "Failed to fetch users from MusicManagement, status: " << msg.status());
            }
        };

        request.onFailureFunc = []() {
            LMS_LOG(AUTH, WARNING, "Failed to fetch users from MusicManagement, connection error");
        };

        _client->sendGETRequest(std::move(request));
    }
    } // namespace musicManagement
} // namespace lms::auth
