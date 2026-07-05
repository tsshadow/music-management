#include "MumaResource.hpp"

#include <Wt/Http/Request.h>
#include <Wt/Http/Response.h>
#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Parser.h>
#include <boost/asio/ip/address.hpp>

#include "core/IConfig.hpp"
#include "core/Service.hpp"
#include "database/Session.hpp"
#include "database/objects/TrackList.hpp"
#include "database/objects/User.hpp"
#include "database/objects/UIState.hpp"
#include "services/auth/IPasswordService.hpp"

namespace lms::api::muma
{
    MumaResource::MumaResource(db::IDb& db)
        : _db{ db }
    {
    }

    MumaResource::~MumaResource()
    {
    }

    void MumaResource::handleRequest(const Wt::Http::Request& request, Wt::Http::Response& response)
    {
        db::Session session{ _db };
        auto transaction{ session.createReadTransaction() };

        std::string pathInfo = request.pathInfo();
        response.setMimeType("application/json");

        const std::string configMumaApiKey{ core::Service<core::IConfig>::get()->getString("api-key", "") };

        if (pathInfo == "/api/auth/login")
        {
            Wt::Json::Object root;
            std::string jsonStr((std::istreambuf_iterator<char>(request.in())), std::istreambuf_iterator<char>());
            Wt::Json::ParseError error;
            if (!Wt::Json::parse(jsonStr, root, error))
            {
                response.setStatus(400);
                response.out() << "Invalid JSON";
                return;
            }

            std::string username = root.get("username").toString().orIfNull("");
            std::string password = root.get("password").toString().orIfNull("");

            db::User::pointer dbUser = db::User::find(session, username);
            if (dbUser)
            {
                if (auto passwordService{ core::Service<auth::IPasswordService>::get() })
                {
                    const auto passwordResult{ passwordService->checkUserPassword(boost::asio::ip::make_address(request.clientAddress()), username, password) };
                    if (passwordResult.state == auth::IPasswordService::CheckResult::State::Granted)
                    {
                        Wt::Json::Object result;
                        result["id"] = Wt::Json::Value((long long)dbUser->getId().getValue());
                        result["username"] = Wt::Json::Value(std::string{ dbUser->getLoginName() });
                        result["display_name"] = Wt::Json::Value(std::string{ dbUser->getLoginName() });
                        result["is_admin"] = Wt::Json::Value(dbUser->isAdmin());
                        result["api_key"] = Wt::Json::Value(configMumaApiKey);
                        response.out() << Wt::Json::serialize(result);
                        return;
                    }
                }
            }

            response.setStatus(401);
            response.out() << "Invalid credentials";
            return;
        }

        // Simple auth for other endpoints
        const std::string* apiKeyParam = request.getParameter("apiKey");
        const std::string* userParam = request.getParameter("u");
        const std::string xApiKeyHeader = request.headerValue("X-API-Key");

        bool authenticated = false;
        if (!xApiKeyHeader.empty() && configMumaApiKey != "" && xApiKeyHeader == configMumaApiKey)
            authenticated = true;
        else if (apiKeyParam && configMumaApiKey != "" && *apiKeyParam == configMumaApiKey)
            authenticated = true;

        if (!authenticated)
        {
            response.setStatus(401);
            response.out() << "Unauthorized";
            return;
        }

        db::User::pointer dbUser;
        if (userParam)
            dbUser = db::User::find(session, *userParam);

        if (!dbUser)
        {
            response.setStatus(401);
            response.out() << "User not found";
            return;
        }

        if (pathInfo.find("/users/") == 0)
        {
            // /users/{user_id}/settings/{app_id}
            std::string remaining = pathInfo.substr(7);
            size_t slashPos = remaining.find("/settings/");
            if (slashPos != std::string::npos)
            {
                std::string userIdStr = remaining.substr(0, slashPos);
                std::string appId = remaining.substr(slashPos + 10);
                
                db::UserId userId{ std::stoll(userIdStr) };
                if (userId != dbUser->getId() && !dbUser->isAdmin())
                {
                    response.setStatus(403);
                    response.out() << "Forbidden";
                    return;
                }

                if (request.method() == "GET")
                {
                    db::UIState::pointer state = db::UIState::find(session, "muma_settings_" + appId, userId);
                    Wt::Json::Object result;
                    result["settings"] = state ? Wt::Json::Value(std::string{ state->getValue() }) : Wt::Json::Value::Null;
                    response.out() << Wt::Json::serialize(result);
                }
                else if (request.method() == "POST")
                {
                    auto writeTransaction{ session.createWriteTransaction() };
                    
                    Wt::Json::Object root;
                    std::string jsonStr((std::istreambuf_iterator<char>(request.in())), std::istreambuf_iterator<char>());
                    Wt::Json::ParseError error;
                    if (!Wt::Json::parse(jsonStr, root, error))
                    {
                        response.setStatus(400);
                        response.out() << "Invalid JSON";
                        return;
                    }

                    std::string settings = root.get("settings").toString().orIfNull("");
                    
                    db::UIState::pointer state = db::UIState::find(session, "muma_settings_" + appId, userId);
                    if (state)
                    {
                        state.modify()->setValue(settings);
                    }
                    else
                    {
                        db::User::pointer targetUser = db::User::find(session, userId);
                        if (targetUser)
                        {
                            auto state = session.create<db::UIState>("muma_settings_" + appId, targetUser);
                            state.modify()->setValue(settings);
                        }
                    }
                    response.out() << "{\"status\":\"ok\"}";
                }
            }
        }
        else
        {
            response.setStatus(404);
        }
    }
}
