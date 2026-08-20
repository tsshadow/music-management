#include "api/muma/MumaResource.hpp"

#include <Wt/Http/Request.h>
#include <Wt/Http/Response.h>
#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Json/Parser.h>
#include <Wt/Utils.h>
#include <boost/asio/ip/address.hpp>
#include <algorithm>
#include <array>
#include <cctype>
#include <chrono>
#include <cstring>
#include <memory>

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
#include "services/auth/IAuthTokenService.hpp"
#include "core/http/ProxyContinuation.hpp"
#include "services/auth/IUserSynchronizer.hpp"
#include "services/auth/IPasswordService.hpp"
#include "services/scanner/IScannerService.hpp"

namespace lms::api::muma
{
    namespace
    {
        // How long a proxied call waits on MuMa before the caller is told it timed out. These are
        // deadlines on an answer, not on a thread: since these handlers park on a Wt continuation,
        // waiting costs a connection, not one of the few HTTP server threads.
        constexpr std::chrono::seconds mumaProxyDeadline{ 10 };
        constexpr std::chrono::seconds mumaRefreshDeadline{ 15 };
        constexpr std::chrono::seconds mumaGenericProxyDeadline{ 30 };
    } // namespace

    MumaResource::MumaResource(boost::asio::io_context& ioContext, db::IDb& db, auth::IUserSynchronizer& userSynchronizer)
        : _ioContext{ ioContext }
        , _db{ db }
        , _userSynchronizer{ userSynchronizer }
    {
        _mumaApiUrl = std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") };
        if (_mumaApiUrl.empty())
        {
            _mumaApiUrl = std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-url", "") };
        }

        if (!_mumaApiUrl.empty())
        {
            size_t pos = _mumaApiUrl.find("/api");
            if (pos != std::string::npos)
                _mumaApiUrl = _mumaApiUrl.substr(0, pos);

            if (_mumaApiUrl.back() == '/')
                _mumaApiUrl.pop_back();

            LMS_LOG(API_SUBSONIC, INFO, "MumaResource: Using MuMa API URL: " << _mumaApiUrl);
            _httpClient = core::http::createClient(ioContext, _mumaApiUrl);
        }

        _mumaApiKey = std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") };
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

                    // 401 here would tell the client its stored credentials are bad and make it
                    // throw them away, when in fact we never managed to check them.
                    if (passwordResult.state == auth::IPasswordService::CheckResult::State::BackendError)
                    {
                        LMS_LOG(API_SUBSONIC, ERROR, "MumaResource: cannot reach the authentication backend for user '" << username << "'");
                        response.setStatus(503);
                        response.out() << "Authentication backend unavailable";
                        return;
                    }
                }
            }

            response.setStatus(401);
            response.out() << "Invalid credentials";
            return;
        }

        // Public, unauthenticated auth endpoints: these are the entry points for
        // users who don't have any credentials yet (initial setup, and the
        // Google Sign-In / access-request flow for a brand-new Google identity),
        // so they must be reachable without an existing Subsonic apiKey/u+p.
        // They are simply proxied through, unauthenticated, to MuMa below (same
        // generic "/api/" proxy used for everything else), which does its own
        // validation (Google ID token verification, setup-already-done checks, ...).
        static const std::array<std::string_view, 4> publicAuthPaths{
            "/api/auth/setup-status",
            "/api/auth/setup",
            "/api/auth/google",
            "/api/auth/access-request",
        };
        const bool isPublicAuthPath = std::find(publicAuthPaths.begin(), publicAuthPaths.end(), pathInfo) != publicAuthPaths.end();

        // Simple auth for other endpoints
        const std::string* apiKeyParam = request.getParameter("apiKey");
        const std::string* userParam = request.getParameter("u");
        const std::string* passParam = request.getParameter("p");
        const std::string xApiKeyHeader = request.headerValue("X-API-Key");

        // NOTE: matching the single, shared `configMumaApiKey` (LMS_API_KEY) is
        // only ONE valid way in -- it's what `/api/auth/login` (handled locally,
        // just above) hands back to every locally-authenticated Subsonic user.
        // But MuMa (music_manager) also issues its own, per-user API keys (e.g.
        // to Google Sign-In users via `/api/auth/google`/`/api/auth/access-request`,
        // see the public-path list above), which will never equal the shared
        // key. Any non-empty key is therefore accepted here and simply
        // forwarded on to MuMa for every proxied "/api/" endpoint below --
        // MuMa re-validates X-API-Key itself on every request (see
        // rbac.require_permission / verify_token) and is the real
        // authority here; this local check only exists to keep fully
        // anonymous requests (no key, no Subsonic u/p) from being proxied at all.
        bool authenticated = isPublicAuthPath;
        if (!xApiKeyHeader.empty())
            authenticated = true;
        else if (apiKeyParam && !apiKeyParam->empty())
            authenticated = true;
        
        db::User::pointer dbUser;
        if (userParam)
        {
            dbUser = db::User::find(session, *userParam);
        }

        bool authBackendUnavailable = false;
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
                    authBackendUnavailable = passwordResult.state == auth::IPasswordService::CheckResult::State::BackendError;
                    LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: Authentication failed for user '" << *userParam << "' (state: " << static_cast<int>(passwordResult.state) << ")");
                }
            }
        }

        if (!authenticated)
        {
            // Say "we could not check" rather than "you are not allowed", so the client keeps the
            // credentials it has and retries instead of logging the user out.
            if (authBackendUnavailable)
            {
                LMS_LOG(API_SUBSONIC, ERROR, "MumaResource: authentication backend unavailable for " << pathInfo);
                response.setStatus(503);
                response.out() << "Authentication backend unavailable";
                return;
            }

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

        // Subsonic API tokens are administered here, from the management UI, rather
        // than being self-service in the player's settings screen: they are what
        // external clients (Ultrasonic, Magna, ...) authenticate with, so handing
        // them out is an admin task. Handled locally (not proxied to MuMa) because
        // the tokens live in this server's own auth-token store.
        if (pathInfo == "/api/admin/subsonic-token")
        {
            if (!dbUser || !dbUser->isAdmin())
            {
                response.setStatus(403);
                response.out() << "Forbidden";
                return;
            }

            const std::string* targetParam{ request.getParameter("username") };
            if (!targetParam || targetParam->empty())
            {
                response.setStatus(400);
                response.out() << "username is required";
                return;
            }

            db::User::pointer targetUser{ db::User::find(session, *targetParam) };
            if (!targetUser)
            {
                response.setStatus(404);
                response.out() << "User not found";
                return;
            }

            auto& authTokenService{ *core::Service<auth::IAuthTokenService>::get() };

            if (request.method() == "GET")
            {
                std::string token;
                authTokenService.visitAuthTokens("subsonic", targetUser->getId(), [&](const auth::IAuthTokenService::AuthTokenInfo&, std::string_view storedToken) {
                    if (token.empty())
                        token = storedToken;
                });

                Wt::Json::Object result;
                result["username"] = Wt::Json::Value(std::string{ targetUser->getLoginName() });
                result["token"] = Wt::Json::Value(token);
                response.out() << Wt::Json::serialize(result);
                return;
            }

            if (request.method() == "PUT" || request.method() == "POST")
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

                const std::string token = root.get("token").toString().orIfNull("");

                // An empty token means "revoke": every existing token is dropped and
                // no new one is created, so the user's external clients stop working
                // until a new token is issued.
                authTokenService.clearAuthTokens("subsonic", targetUser->getId());
                if (!token.empty())
                    authTokenService.createAuthToken("subsonic", targetUser->getId(), token);

                Wt::Json::Object result;
                result["username"] = Wt::Json::Value(std::string{ targetUser->getLoginName() });
                result["token"] = Wt::Json::Value(token);
                response.out() << Wt::Json::serialize(result);
                return;
            }

            response.setStatus(405);
            response.out() << "Method not allowed";
            return;
        }

        if (pathInfo.find("/api/artists/") == 0)
        {
            size_t start = std::string("/api/artists/").length();
            const std::string remainder = pathInfo.substr(start);
            // Only intercept the two path shapes this handler actually implements: a straight
            // artist image request ("...*/image") and a plain (optionally slug-"-"-prefixed)
            // numeric artist ID with no further path segments (used by the player's own Artist
            // detail view for a native genre lookup, e.g. "/api/artists/123" or "/api/artists/some-slug-123").
            // Any other "/api/artists/*" path (e.g. "/images/stats", "/search", "/search-all",
            // "/fetch-progress", "/fetch-missing", "/{id}/fetch-image") must fall through to the
            // generic "/api/*" MuMa proxy further below instead of being wrongly swallowed here
            // and rejected with "Invalid artist ID" (see docs/bug-reports/006-artist-images-tab-zero-stats.md).
            // NOTE: it is not enough to just check for the absence of a '/' - static routes like
            // "search", "search-all", "fetch-progress" and "fetch-missing" also have no '/', so the
            // remaining (post slug-prefix) segment must actually be all-digits to count as an ID.
            std::string idCandidate = remainder;
            if (const size_t pos{ idCandidate.find('-') }; pos != std::string::npos)
                idCandidate = idCandidate.substr(pos + 1);
            const bool isNumericId = !idCandidate.empty() && std::all_of(idCandidate.begin(), idCandidate.end(), [](unsigned char c) { return std::isdigit(c) != 0; });
            const bool isPlainIdSegment = isNumericId && !pathInfo.ends_with("/image") && remainder.find('/') == std::string::npos;
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

            core::http::ClientGETRequestParameters getParams;
            getParams.relativeUrl = relativeUrl;
            // Artwork is the one thing here nobody is waiting on.
            getParams.priority = core::http::ClientRequestParameters::Priority::Low;
            if (!_mumaApiKey.empty())
                getParams.headers.push_back(Wt::Http::Message::Header("X-API-Key", _mumaApiKey));

            const auto answer{ core::http::proxyRequest(request, response, _ioContext, *_httpClient, std::move(getParams), mumaProxyDeadline) };
            if (!answer)
                return; // parked on a continuation; nothing may be written yet

            response.setStatus(answer->status);
            if (answer->status == 200)
            {
                response.setMimeType(answer->contentType);
                response.out() << answer->body;
            }
            else if (answer->status == 504)
            {
                LMS_LOG(API_SUBSONIC, ERROR, "MumaResource: Timeout waiting for MuMa response for artist '" << artistName << "'");
                response.out() << "Timeout waiting for MuMa";
            }
            else
            {
                LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: MuMa returned status " << answer->status << " for artist '" << artistName << "'");
                response.out() << "MuMa returned error: " << answer->status;
            }
            return;
        }
        else if (isPlainIdSegment)
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

            core::http::ClientPOSTRequestParameters postParams;
            postParams.relativeUrl = relativeUrl;
            if (!_mumaApiKey.empty())
                postParams.message.addHeader("X-API-Key", _mumaApiKey);

            const auto answer{ core::http::proxyRequest(request, response, _ioContext, *_httpClient, std::move(postParams), mumaRefreshDeadline) };
            if (!answer)
                return; // parked on a continuation; nothing may be written yet

            response.setStatus(answer->status);
            if (answer->status == 200)
            {
                response.out() << "{\"status\":\"ok\"}";
            }
            else if (answer->status == 504)
            {
                LMS_LOG(API_SUBSONIC, ERROR, "MumaResource: Timeout waiting for MuMa response for track refresh: " << absolutePath);
                response.out() << "{\"status\":\"error\", \"detail\": \"Timeout waiting for MuMa\"}";
            }
            else
            {
                LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: MuMa returned status " << answer->status << " for track refresh: " << absolutePath);
                response.out() << "{\"status\":\"error\", \"detail\": \"MuMa returned " << answer->status << "\"}";
            }
            return;
        }

        if (pathInfo.find("/users/") == 0)
        {
            if (pathInfo == "/users/sync")
            {
                _userSynchronizer.syncUsers();
                response.out() << "{\"status\":\"ok\"}";
                return;
            }

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
                    if (!_httpClient)
                    {
                        response.setStatus(500);
                        return;
                    }

                    core::http::ClientGETRequestParameters getParams;
                    getParams.relativeUrl = "/api/users/" + std::to_string(userId->getValue()) + "/settings/" + appId;
                    if (!_mumaApiKey.empty())
                        getParams.headers.push_back(Wt::Http::Message::Header("X-API-Key", _mumaApiKey));

                    const auto answer{ core::http::proxyRequest(request, response, _ioContext, *_httpClient, std::move(getParams), mumaProxyDeadline) };
                    if (!answer)
                        return; // parked on a continuation; nothing may be written yet

                    if (answer->status == 504)
                        response.setStatus(504);
                    else if (answer->status == 200)
                        response.out() << answer->body;
                    else
                        response.out() << "{\"settings\": null}"; // nothing stored for this app is not an error here
                }
                else if (request.method() == "POST")
                {
                    if (!_httpClient)
                    {
                        response.setStatus(500);
                        return;
                    }

                    std::string jsonStr((std::istreambuf_iterator<char>(request.in())), std::istreambuf_iterator<char>());

                    core::http::ClientPOSTRequestParameters postParams;
                    postParams.relativeUrl = "/api/users/" + std::to_string(userId->getValue()) + "/settings/" + appId;
                    if (!_mumaApiKey.empty())
                        postParams.message.addHeader("X-API-Key", _mumaApiKey);
                    postParams.message.addHeader("Content-Type", "application/json");
                    postParams.message.addBodyText(jsonStr);

                    const auto answer{ core::http::proxyRequest(request, response, _ioContext, *_httpClient, std::move(postParams), mumaProxyDeadline) };
                    if (!answer)
                        return; // parked on a continuation; nothing may be written yet

                    response.setStatus(answer->status);
                    if (answer->status != 504)
                        response.out() << "{\"status\":\"ok\"}";
                }
            }
        }
        else if (pathInfo.find("/api/") == 0)
        {
            if (!_httpClient)
            {
                response.setStatus(500);
                response.out() << "Music Management not configured";
                return;
            }

            // Generic proxy for all other /api/ calls
            std::shared_ptr<const core::http::ProxyAnswer> answer;

            if (request.method() == "GET")
            {
                core::http::ClientGETRequestParameters getParams;
                getParams.relativeUrl = pathInfo;
                std::string query = request.queryString();
                if (!query.empty())
                    getParams.relativeUrl += "?" + query;

                // Forward the CALLER's own key first (Subsonic-shared LMS key or a
                // per-user MuMa key from Google Sign-In) so MuMa sees the real caller
                // identity/permissions instead of a generic system identity for every
                // request; only fall back to the configured system key when the
                // caller didn't send one at all (e.g. an internal/system-only call).
                if (!xApiKeyHeader.empty())
                    getParams.headers.push_back(Wt::Http::Message::Header("X-API-Key", xApiKeyHeader));
                else if (!_mumaApiKey.empty())
                    getParams.headers.push_back(Wt::Http::Message::Header("X-API-Key", _mumaApiKey));

                // This is a raw pass-through proxy: MuMa's exact status code (401,
                // 403, 404, ...) and body are meaningful to the original caller and
                // must be forwarded verbatim, not collapsed into a generic 502.
                answer = core::http::proxyRequest(request, response, _ioContext, *_httpClient, std::move(getParams), mumaGenericProxyDeadline);
            }
            else if (request.method() == "POST" || request.method() == "PUT" || request.method() == "DELETE")
            {
                core::http::ClientPOSTRequestParameters postParams;
                postParams.relativeUrl = pathInfo;
                std::string query = request.queryString();
                if (!query.empty())
                    postParams.relativeUrl += "?" + query;

                // See the matching comment in the GET branch above: prefer the
                // caller's own key over the system key.
                if (!xApiKeyHeader.empty())
                    postParams.message.addHeader("X-API-Key", xApiKeyHeader);
                else if (!_mumaApiKey.empty())
                    postParams.message.addHeader("X-API-Key", _mumaApiKey);

                std::string contentType = request.headerValue("Content-Type");
                if (!contentType.empty())
                    postParams.message.addHeader("Content-Type", contentType);

                std::string jsonStr((std::istreambuf_iterator<char>(request.in())), std::istreambuf_iterator<char>());
                postParams.message.addBodyText(jsonStr);

                // See the matching comment in the GET branch above: forward MuMa's
                // real status/body verbatim instead of collapsing it into a 502.
                //
                // PUT and DELETE go out as POSTs: the client wrapper has no verb of its own for
                // them. That was already true before and is not what this change is about.
                answer = core::http::proxyRequest(request, response, _ioContext, *_httpClient, std::move(postParams), mumaGenericProxyDeadline);
            }
            else
            {
                response.setStatus(405);
                response.out() << "Method Not Allowed";
                return;
            }

            if (!answer)
                return; // parked on a continuation; nothing may be written yet

            response.setStatus(answer->status);
            if (answer->status == 504)
                response.out() << "Gateway Timeout";
            else if (answer->status == 502)
                response.out() << "Bad Gateway";
            else
                response.out() << answer->body;
            return;
        }
        else
        {
            response.setStatus(404);
        }
    }
}
