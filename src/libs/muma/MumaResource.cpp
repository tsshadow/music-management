#include "api/muma/MumaResource.hpp"

#include <Wt/Http/Request.h>
#include <Wt/Http/Response.h>
#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Parser.h>
#include <Wt/Utils.h>
#include <boost/asio/ip/address.hpp>
#include <future>
#include <cstring>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/String.hpp"
#include "core/Service.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/MediaLibrary.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackList.hpp"
#include "database/objects/User.hpp"
#include "database/objects/UIState.hpp"
#include "services/auth/IPasswordService.hpp"
#include "services/scanner/IScannerService.hpp"

namespace lms::api::muma
{
    MumaResource::MumaResource(boost::asio::io_context& ioContext, db::IDb& db)
        : _db{ db }
    {
        _mumaApiUrl = std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") };
        if (_mumaApiUrl.empty())
        {
            std::string apiUrl = std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-url", "") };
            size_t pos = apiUrl.find("/api/");
            if (pos != std::string::npos)
                _mumaApiUrl = apiUrl.substr(0, pos);
            else
                _mumaApiUrl = apiUrl;
        }

        if (!_mumaApiUrl.empty() && _mumaApiUrl.back() == '/')
            _mumaApiUrl.pop_back();

        _mumaApiKey = std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") };
        
        if (!_mumaApiUrl.empty())
        {
            LMS_LOG(API_SUBSONIC, INFO, "MumaResource: Using MuMa API URL: " << _mumaApiUrl);
            _httpClient = core::http::createClient(ioContext, _mumaApiUrl);
        }
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

        const std::string configMumaApiKey = std::string{ core::Service<core::IConfig>::get()->getString("api-key", "") };

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
        const std::string* passParam = request.getParameter("p");
        const std::string xApiKeyHeader = request.headerValue("X-API-Key");

        bool authenticated = false;
        if (!xApiKeyHeader.empty() && !configMumaApiKey.empty() && xApiKeyHeader == configMumaApiKey)
            authenticated = true;
        else if (apiKeyParam && !configMumaApiKey.empty() && *apiKeyParam == configMumaApiKey)
            authenticated = true;
        
        db::User::pointer dbUser;
        if (userParam)
        {
            dbUser = db::User::find(session, *userParam);
        }

        if (!authenticated && userParam && passParam)
        {
            std::string password = *passParam;
            if (password.starts_with("enc:"))
            {
                if (auto decoded = core::stringUtils::stringFromHex(password.substr(4)))
                    password = *decoded;
            }

            if (auto passwordService{ core::Service<auth::IPasswordService>::get() })
            {
                const auto passwordResult{ passwordService->checkUserPassword(boost::asio::ip::make_address(request.clientAddress()), *userParam, password) };
                if (passwordResult.state == auth::IPasswordService::CheckResult::State::Granted)
                {
                    authenticated = true;
                    if (!dbUser)
                        dbUser = db::User::find(session, passwordResult.userId);
                }
                else
                {
                    LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: Authentication failed for user '" << *userParam << "' (state: " << static_cast<int>(passwordResult.state) << ")");
                }
            }
        }

        if (!authenticated)
        {
            LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: Unauthorized access attempt to " << pathInfo);
            response.setStatus(401);
            response.out() << "Unauthorized";
            return;
        }

        if (pathInfo == "/api/admin/libraries")
        {
            if (!dbUser || !dbUser->isAdmin())
            {
                response.setStatus(403);
                response.out() << "Forbidden";
                return;
            }

            if (request.method() == "GET")
            {
                Wt::Json::Array result;
                db::MediaLibrary::find(session, [&](const db::MediaLibrary::pointer& lib) {
                    Wt::Json::Object obj;
                    obj["id"] = Wt::Json::Value((long long)lib->getId().getValue());
                    obj["name"] = Wt::Json::Value(std::string{ lib->getName() });
                    obj["path"] = Wt::Json::Value(std::string{ lib->getPath() });
                    result.push_back(std::move(obj));
                });
                response.out() << Wt::Json::serialize(result);
                return;
            }
            else if (request.method() == "POST")
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

                std::string name = root.get("name").toString().orIfNull("");
                std::string path = root.get("path").toString().orIfNull("");

                if (name.empty() || path.empty())
                {
                    response.setStatus(400);
                    response.out() << "Name and path are required";
                    return;
                }

                {
                    auto writeTransaction{ session.createWriteTransaction() };
                    session.create<db::MediaLibrary>(name, path);
                }

                core::Service<scanner::IScannerService>::get()->requestReload();
                response.out() << "{\"status\":\"ok\"}";
                return;
            }
        }

        if (pathInfo.find("/api/admin/libraries/") == 0 && request.method() == "DELETE")
        {
            if (!dbUser || !dbUser->isAdmin())
            {
                response.setStatus(403);
                response.out() << "Forbidden";
                return;
            }

            std::string idStr = pathInfo.substr(21);
            db::MediaLibraryId id;
            try {
                id = db::MediaLibraryId{ std::stoll(idStr) };
            } catch (...) {
                response.setStatus(400);
                response.out() << "Invalid library ID";
                return;
            }

            {
                auto writeTransaction{ session.createWriteTransaction() };
                if (auto lib = db::MediaLibrary::find(session, id))
                    lib.remove();
                else
                {
                    response.setStatus(404);
                    response.out() << "Library not found";
                    return;
                }
            }

            core::Service<scanner::IScannerService>::get()->requestReload();
            response.out() << "{\"status\":\"ok\"}";
            return;
        }

        if (pathInfo.find("/api/artists/") == 0)
        {
            size_t start = std::string("/api/artists/").length();
            if (pathInfo.ends_with("/image"))
            {
                size_t end = pathInfo.length() - std::string("/image").length();
                if (end <= start)
                {
                    response.setStatus(400);
                    response.out() << "Invalid artist name in path";
                    return;
                }

                std::string artistName = pathInfo.substr(start, end - start);
            // Decode it first as Wt might have decoded it if it was a path parameter (but Wt::WResource doesn't do that automatically for us here)
            // Actually pathInfo is already decoded by Wt!
            
            if (!_httpClient)
            {
                response.setStatus(500);
                response.out() << "Music Management not configured";
                return;
            }

            // Encode for MuMa path parameter (FastAPI expects %20 for spaces, not +)
            std::string encodedName = Wt::Utils::urlEncode(artistName);
            for (size_t i = 0; i < encodedName.length(); ++i) {
                if (encodedName[i] == '+') {
                    encodedName.replace(i, 1, "%20");
                }
            }
            std::string relativeUrl = "/api/artists/" + encodedName + "/image";

            // We use a promise/future to wait for the result in this simple implementation
            // Note: This blocks the current thread, but since images are small and MuMa is usually local, it's acceptable here
            struct ProxyResult {
                int status;
                std::string contentType;
                std::vector<std::byte> data;
            };
            auto resultPromise = std::make_shared<std::promise<ProxyResult>>();
            auto resultFuture = resultPromise->get_future();

            core::http::ClientGETRequestParameters getParams;
            getParams.relativeUrl = relativeUrl;
            if (!_mumaApiKey.empty())
                getParams.headers.push_back(Wt::Http::Message::Header("X-API-Key", _mumaApiKey));

            getParams.onSuccessFunc = [resultPromise](const Wt::Http::Message& msg) {
                ProxyResult res;
                res.status = msg.status();
                if (const std::string* contentType = msg.getHeader("Content-Type"))
                    res.contentType = *contentType;
                const std::string& body = msg.body();
                res.data.resize(body.size());
                std::memcpy(res.data.data(), body.data(), body.size());
                resultPromise->set_value(std::move(res));
            };
            getParams.onFailureFunc = [resultPromise]() {
                ProxyResult res;
                res.status = 502; // Bad Gateway
                resultPromise->set_value(std::move(res));
            };

            _httpClient->sendGETRequest(std::move(getParams));

            if (resultFuture.wait_for(std::chrono::seconds(10)) == std::future_status::ready)
            {
                ProxyResult res = resultFuture.get();
                response.setStatus(res.status);
                if (res.status == 200)
                {
                    response.setMimeType(res.contentType);
                    response.out().write(reinterpret_cast<const char*>(res.data.data()), res.data.size());
                }
                else
                {
                    LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: MuMa returned status " << res.status << " for artist '" << artistName << "'");
                    response.out() << "MuMa returned error: " << res.status;
                }
            }
            else
            {
                LMS_LOG(API_SUBSONIC, ERROR, "MumaResource: Timeout waiting for MuMa response for artist '" << artistName << "'");
                response.setStatus(504); // Gateway Timeout
                response.out() << "Timeout waiting for MuMa";
            }
            return;
        }
        else
        {
            std::string artistIdStr = pathInfo.substr(start);
            if (const size_t pos{ artistIdStr.find('-') }; pos != std::string::npos)
                artistIdStr = artistIdStr.substr(pos + 1);

            db::ArtistId artistId;
            try
            {
                artistId = db::ArtistId{ std::stoll(artistIdStr) };
            }
            catch (const std::exception&)
            {
                response.setStatus(400);
                response.out() << "Invalid artist ID";
                return;
            }

            db::Artist::pointer artist = db::Artist::find(session, artistId);
            if (!artist)
            {
                response.setStatus(404);
                response.out() << "Artist not found";
                return;
            }

            Wt::Json::Object result;
            result["id"] = Wt::Json::Value(artistIdStr);
            result["name"] = Wt::Json::Value(std::string{ artist->getName() });

            Wt::Json::Array genres;
            if (const auto genreType{ db::ClusterType::find(session, "GENRE") })
            {
                const std::array<db::ClusterTypeId, 1> clusterTypeIds{ genreType->getId() };
                const std::vector<std::vector<db::Cluster::pointer>> clusterGroups{ artist->getClusterGroups(clusterTypeIds, 10) };
                if (!clusterGroups.empty())
                {
                    for (const db::Cluster::pointer& cluster : clusterGroups.front())
                    {
                        Wt::Json::Object genre;
                        genre["name"] = Wt::Json::Value(std::string{ cluster->getName() });
                        genres.push_back(std::move(genre));
                    }
                }
            }
            result["genres"] = std::move(genres);

            response.out() << Wt::Json::serialize(result);
            return;
        }
    }

        if (pathInfo.find("/api/tracks/") == 0 && pathInfo.ends_with("/refresh"))
        {
            size_t start = std::string("/api/tracks/").length();
            size_t end = pathInfo.length() - std::string("/refresh").length();
            if (end <= start)
            {
                response.setStatus(400);
                response.out() << "Invalid track ID in path";
                return;
            }

            std::string trackIdStr = pathInfo.substr(start, end - start);
            if (const size_t pos{ trackIdStr.find('-') }; pos != std::string::npos)
                trackIdStr = trackIdStr.substr(pos + 1);

            db::TrackId trackId;
            try
            {
                trackId = db::TrackId{ std::stoll(trackIdStr) };
            }
            catch (const std::exception&)
            {
                response.setStatus(400);
                response.out() << "Invalid track ID format";
                return;
            }

            db::Track::pointer track = db::Track::find(session, trackId);
            if (!track)
            {
                response.setStatus(404);
                response.out() << "Track not found in LMS database";
                return;
            }

            if (!_httpClient)
            {
                response.setStatus(500);
                response.out() << "Music Management not configured";
                return;
            }

            std::string absolutePath = track->getAbsoluteFilePath().string();
            std::string encodedPath = Wt::Utils::urlEncode(absolutePath);
            for (size_t i = 0; i < encodedPath.length(); ++i) {
                if (encodedPath[i] == '+') {
                    encodedPath.replace(i, 1, "%20");
                }
            }
            std::string relativeUrl = "/api/library/tracks/rerun-parse-path?path=" + encodedPath;

            auto resultPromise = std::make_shared<std::promise<int>>();
            auto resultFuture = resultPromise->get_future();

            core::http::ClientPOSTRequestParameters postParams;
            postParams.relativeUrl = relativeUrl;
            if (!_mumaApiKey.empty())
                postParams.message.addHeader("X-API-Key", _mumaApiKey);

            postParams.onSuccessFunc = [resultPromise](const Wt::Http::Message& msg) {
                resultPromise->set_value(msg.status());
            };
            postParams.onFailureFunc = [resultPromise]() {
                resultPromise->set_value(502);
            };

            _httpClient->sendPOSTRequest(std::move(postParams));

            if (resultFuture.wait_for(std::chrono::seconds(15)) == std::future_status::ready)
            {
                int status = resultFuture.get();
                response.setStatus(status);
                if (status == 200)
                    response.out() << "{\"status\":\"ok\"}";
                else
                {
                    LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: MuMa returned status " << status << " for track refresh: " << absolutePath);
                    response.out() << "{\"status\":\"error\", \"detail\": \"MuMa returned " << status << "\"}";
                }
            }
            else
            {
                LMS_LOG(API_SUBSONIC, ERROR, "MumaResource: Timeout waiting for MuMa response for track refresh: " << absolutePath);
                response.setStatus(504);
                response.out() << "{\"status\":\"error\", \"detail\": \"Timeout waiting for MuMa\"}";
            }
            return;
        }

        if (pathInfo.find("/users/") == 0)
        {
            if (!dbUser)
            {
                response.setStatus(401);
                response.out() << "User not found";
                return;
            }
            // /users/{user_id}/settings/{app_id}
            std::string remaining = pathInfo.substr(7);
            size_t slashPos = remaining.find("/settings/");
            if (slashPos != std::string::npos)
            {
                std::string userIdStr = remaining.substr(0, slashPos);
                if (const size_t pos{ userIdStr.find('-') }; pos != std::string::npos)
                    userIdStr = userIdStr.substr(pos + 1);

                std::string appId = remaining.substr(slashPos + 10);
                
                std::optional<db::UserId> userId;
                try
                {
                    userId = db::UserId{ std::stoll(userIdStr) };
                }
                catch (const std::exception&)
                {
                    response.setStatus(400);
                    response.out() << "Invalid User ID";
                    return;
                }

                if (*userId != dbUser->getId() && !dbUser->isAdmin())
                {
                    response.setStatus(403);
                    response.out() << "Forbidden";
                    return;
                }

                if (request.method() == "GET")
                {
                    db::UIState::pointer state = db::UIState::find(session, "muma_settings_" + appId, *userId);
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
                    
                    db::UIState::pointer state = db::UIState::find(session, "muma_settings_" + appId, *userId);
                    if (state)
                    {
                        state.modify()->setValue(settings);
                    }
                    else
                    {
                        db::User::pointer targetUser = db::User::find(session, *userId);
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
