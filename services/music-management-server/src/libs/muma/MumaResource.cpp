#include "api/muma/MumaResource.hpp"

#include "api/muma/PathEncoding.hpp"
#include "api/muma/Routing.hpp"

#include <Wt/Http/Request.h>
#include <Wt/Http/Response.h>
#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>
#include <Wt/Json/Serializer.h>
#include <Wt/Utils.h>
#include <algorithm>
#include <array>
#include <boost/asio/ip/address.hpp>
#include <cctype>
#include <cstring>
#include <future>
#include <iterator>
#include <memory>
#include <ranges>
#include <span>
#include <string_view>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Md5.hpp"
#include "core/Service.hpp"
#include "core/String.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/AuthToken.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/MediaLibrary.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackList.hpp"
#include "database/objects/UIState.hpp"
#include "database/objects/User.hpp"
#include "services/auth/IAuthTokenService.hpp"
#include "services/auth/IPasswordService.hpp"
#include "services/auth/IUserSynchronizer.hpp"
#include "services/scanner/IScannerService.hpp"

namespace lms::api::muma
{
    namespace
    {
        // A news bulletin is a ten-minute recording, around 15 MB. Nothing else behind this
        // proxy answers with a file, so it is the only response collected in chunks rather
        // than left to Wt's own buffer. Reserved up front so the appends do not keep
        // reallocating a buffer that ends up this size anyway.
        constexpr std::size_t newsBulletinBufferSize{ std::size_t{ 24 } * 1024 * 1024 };

        // Collect a bulletin ourselves instead of letting Wt buffer it. Wt appends every read
        // into the response message, and the cost of that grows with what is already there:
        // measured against prod, the transfer starts at 1 MB/s and decays to ~100 KB/s, so 15 MB
        // took about 150 seconds. The send queue sends one request at a time, so for all of those
        // seconds every other call to MuMa -- artist images, settings -- timed out behind it, and
        // the browser had long since been answered with a 504. Setting onChunkReceived makes Wt
        // skip its own accumulation entirely (it only appends while a maximum response size is
        // set, and streaming clears it) and hand the chunks here, where appending into a reserved
        // string is linear.
        // The proxy's answer to its caller: MuMa's status, content type and body.
        struct GenericResult
        {
            int status;
            std::string contentType;
            std::string body;
        };

        // A streamed response leaves msg.body() empty by design, so the chunks collected by
        // collectResponseInChunks are the body. Built here rather than inline because clang-tidy
        // measures handleRequest's complexity and the baseline holds it at exactly today's number.
        core::http::ClientRequestParameters::OnSuccessFunc makeGenericSuccessHandler(std::shared_ptr<std::promise<GenericResult>> resultPromise, std::shared_ptr<std::string> streamedBody)
        {
            return [resultPromise = std::move(resultPromise), streamedBody = std::move(streamedBody)](const Wt::Http::Message& msg) {
                const std::string* contentType{ msg.getHeader("Content-Type") };
                resultPromise->set_value({ msg.status(), contentType ? *contentType : std::string{}, streamedBody->empty() ? msg.body() : std::move(*streamedBody) });
            };
        }

        bool isNewsBulletin(std::string_view pathInfo)
        {
            return pathInfo.starts_with("/api/news/bulletins/");
        }

        void collectResponseInChunks(core::http::ClientGETRequestParameters& params, std::shared_ptr<std::string> body)
        {
            body->reserve(newsBulletinBufferSize);
            params.onChunkReceived = [body = std::move(body)](std::span<const std::byte> chunk) {
                // Byte at a time rather than memcpy or a cast: the checks that apply here rule each
                // other's escape out -- no reinterpret_cast, no route through void*, no pointer
                // arithmetic -- and the buffer is reserved, so this stays linear.
                std::ranges::transform(chunk, std::back_inserter(*body), [](std::byte value) {
                    return std::to_integer<char>(value);
                });
                return core::http::ClientRequestParameters::ChunckReceivedResult::Continue;
            };
        }

        // A refusal is over in milliseconds: the calls holding the gate are round trips.
        // Say when to come back rather than leave the client guessing. Only these local
        // refusals carry the header -- an upstream 503 is forwarded verbatim and says
        // nothing about whether a retry is safe.
        void refuseAsBusy(Wt::Http::Response& response, std::string_view body)
        {
            response.addHeader("Retry-After", "1");
            response.setStatus(503);
            response.out() << body;
        }

        // At most half the HTTP thread pool may be waiting on MuMa, so the other half is always
        // there to serve everything else. Mirrors getThreadCount() in main.cpp, which is what sets
        // the pool size Wt actually runs with.
        std::size_t getMumaCallLimit()
        {
            const unsigned long configured{ core::Service<core::IConfig>::get()->getULong("http-server-thread-count", 0) };
            const unsigned long threadCount{ configured ? configured : std::max<unsigned long>(2, std::thread::hardware_concurrency()) };

            return std::max<std::size_t>(1, threadCount / 2);
        }

        // How long MuMa's word on a key is trusted before it is asked again. It is also how long a
        // revoked key keeps opening this server's own routes, which is why it is short; a
        // /users/sync from MuMa clears the cache at once.
        constexpr std::chrono::seconds keyVerdictTtl{ 60 };
        constexpr std::size_t keyVerdictCacheMaxEntries{ 1024 };
        constexpr std::chrono::seconds keyVerifyTimeout{ 10 };

        /// What the verified caller may do on the routes answered here. The LMS user is looked up
        /// from the verified identity only: the password service's user id for u/p, MuMa's own
        /// answer for a MuMa key. Never from `u`.
        CallerRights resolveCallerRights(db::Session& session, const AuthDecision& auth)
        {
            CallerRights rights;
            rights.method = auth.method;
            if (auth.lmsUserId)
            {
                if (const db::User::pointer user{ db::User::find(session, db::UserId{ *auth.lmsUserId }) })
                {
                    rights.isAdmin = user->isAdmin();
                    if (const std::optional<int> mumaId{ user->getMumaId() })
                        rights.mumaUserId = *mumaId;
                }
            }
            else if (auth.mumaUserId)
            {
                // MuMa's own answer is fresher than the synced LMS copy of the role, so it decides.
                rights.isAdmin = auth.mumaUserIsAdmin;
                rights.mumaUserId = auth.mumaUserId;
            }
            return rights;
        }

        /// Maps the password service's answer onto the shape muma::authenticate expects.
        PasswordCheck toPasswordCheck(const auth::IPasswordService::CheckResult& result)
        {
            switch (result.state)
            {
            case auth::IPasswordService::CheckResult::State::Granted:
                return PasswordCheck::withState(PasswordCheck::State::Granted, result.userId.getValue());
            case auth::IPasswordService::CheckResult::State::BackendError:
                return PasswordCheck::withState(PasswordCheck::State::BackendError);
            case auth::IPasswordService::CheckResult::State::Denied:
            case auth::IPasswordService::CheckResult::State::Throttled:
                break;
            }
            return PasswordCheck::withState(PasswordCheck::State::Denied);
        }

        /// Whether `token` is `md5(t + salt)` for one of the Subsonic API tokens of the enabled LMS
        /// user `loginName` -- the check `SubsonicResource::authenticateUser` makes for `/rest`, so a
        /// URL signed for one is accepted by the other. Local: no call to MuMa. `session` must be
        /// inside a transaction.
        struct TokenSignature
        {
            std::string_view token; // `t`
            std::string_view salt;  // `s`
        };

        PasswordCheck checkSubsonicToken(db::Session& session, std::string_view loginName, const TokenSignature& signature)
        {
            const db::User::pointer user{ db::User::find(session, loginName) };
            if (!user || user->isDisabled())
                return PasswordCheck::withState(PasswordCheck::State::Denied);

            bool matched{};
            db::AuthToken::find(session, "subsonic", user->getId(), [&](const db::AuthToken::pointer& authToken) {
                if (!matched && constantTimeEquals(core::crypto::md5(authToken->getValue() + std::string{ signature.salt }), signature.token))
                    matched = true;
            });
            if (!matched)
                return PasswordCheck::withState(PasswordCheck::State::Denied);
            return PasswordCheck::withState(PasswordCheck::State::Granted, user->getId().getValue());
        }

        /// Replaces every Subsonic token of `userId` with `token`, or only revokes them when
        /// `token` is empty. Returns why the token was refused, in which case nothing changed:
        /// a too-short token must not cost the user the working token they already have.
        std::optional<std::string> replaceSubsonicToken(auth::IAuthTokenService& authTokenService, db::UserId userId, std::string_view token)
        {
            if (auto problem{ subsonicTokenProblem(token) })
                return problem;

            authTokenService.clearAuthTokens("subsonic", userId);
            if (!token.empty())
                authTokenService.createAuthToken("subsonic", userId, token);
            return std::nullopt;
        }
    } // namespace

    MumaResource::MumaResource(boost::asio::io_context& ioContext, db::IDb& db, auth::IUserSynchronizer& userSynchronizer)
        : _db{ db }
        , _userSynchronizer{ userSynchronizer }
        , _mumaCallGate{ getMumaCallLimit() }
        , _keyVerdictCache{ keyVerdictTtl, keyVerdictCacheMaxEntries }
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

    KeyVerdict MumaResource::verifyKeyWithMuma(std::string_view key)
    {
        if (std::optional<KeyVerdict> cached{ _keyVerdictCache.find(key, KeyVerdictCache::Clock::now()) })
            return *cached;

        if (!_httpClient)
            return KeyVerdict::withState(KeyVerdict::State::Unavailable);

        auto resultPromise{ std::make_shared<std::promise<KeyVerdict>>() };
        auto resultFuture{ resultPromise->get_future() };

        core::http::ClientGETRequestParameters params;
        params.relativeUrl = "/api/auth/verify";
        params.priority = core::http::ClientRequestParameters::Priority::High;
        params.headers.emplace_back("X-API-Key", std::string{ key });
        // 401/403 are answers here ("not a valid key"), not transport failures to be retried.
        params.treatAnyStatusAsSuccess = true;
        params.onSuccessFunc = [resultPromise](const Wt::Http::Message& msg) {
            resultPromise->set_value(parseVerifyResponse(msg.status(), msg.body()));
        };
        params.onFailureFunc = [resultPromise]() {
            resultPromise->set_value(KeyVerdict::withState(KeyVerdict::State::Unavailable));
        };

        const auto mumaCallLease{ _mumaCallGate.tryAcquire() };
        if (!mumaCallLease)
        {
            LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: key verification refused, " << _mumaCallGate.getInUseCount() << " of " << _mumaCallGate.getMaxConcurrent() << " calls to MuMa already in flight");
            return KeyVerdict::withState(KeyVerdict::State::Unavailable);
        }

        _httpClient->sendGETRequest(std::move(params));
        if (resultFuture.wait_for(keyVerifyTimeout) != std::future_status::ready)
        {
            LMS_LOG(API_SUBSONIC, ERROR, "MumaResource: timeout waiting for MuMa to verify a key");
            return KeyVerdict::withState(KeyVerdict::State::Unavailable);
        }

        const KeyVerdict verdict{ resultFuture.get() };
        _keyVerdictCache.store(key, verdict, KeyVerdictCache::Clock::now());
        return verdict;
    }

    AuthDecision MumaResource::authenticateRequest(const Wt::Http::Request& request, bool publicAuthPath, db::Session& session)
    {
        const std::string* apiKeyParam{ request.getParameter("apiKey") };
        const std::string* userParam{ request.getParameter("u") };
        const std::string* passParam{ request.getParameter("p") };
        const std::string* tokenParam{ request.getParameter("t") };
        const std::string* saltParam{ request.getParameter("s") };
        const std::string headerKey{ request.headerValue("X-API-Key") };

        RequestCredentials credentials;
        credentials.headerKey = headerKey;
        credentials.isPublicPath = publicAuthPath;
        if (apiKeyParam)
            credentials.paramKey = *apiKeyParam;
        if (userParam)
            credentials.user = *userParam;
        if (passParam)
            credentials.password = *passParam;
        if (tokenParam)
            credentials.token = *tokenParam;
        if (saltParam)
            credentials.salt = *saltParam;

        const std::string lmsApiKey{ core::Service<core::IConfig>::get()->getString("api-key", "") };
        const std::string clientAddress{ request.clientAddress() };

        AuthDecision decision{ authenticate(
            credentials, lmsApiKey, [this](std::string_view key) { return verifyKeyWithMuma(key); },
            [&clientAddress](std::string_view user, std::string_view password) {
                auth::IPasswordService* passwordService{ core::Service<auth::IPasswordService>::get() };
                if (!passwordService)
                    return PasswordCheck{};
                return toPasswordCheck(passwordService->checkUserPassword(boost::asio::ip::make_address(clientAddress), user, password));
            },
            [&session](std::string_view user, std::string_view token, std::string_view salt) {
                return checkSubsonicToken(session, user, TokenSignature{ .token = token, .salt = salt });
            }) };

        if (decision.outcome != AuthDecision::Outcome::Authenticated)
            LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: authentication failed" << (userParam ? " for user '" + *userParam + "'" : std::string{}) << " (outcome: " << static_cast<int>(decision.outcome) << ")");

        return decision;
    }

    void MumaResource::handleRequest(const Wt::Http::Request& request, Wt::Http::Response& response)
    {
        db::Session session{ _db };
        auto transaction{ session.createReadTransaction() };

        std::string pathInfo = request.pathInfo();
        response.setMimeType("application/json");

        // Public, unauthenticated auth endpoints: the entry points for users who have no
        // credentials yet -- the username/password login, initial setup, and the Google
        // Sign-In / access-request flow. They are proxied through, unauthenticated, to MuMa
        // below (the same generic "/api/" proxy used for everything else), which does its own
        // validation and answers with the user's own key. See isPublicAuthPath().
        //
        // Behind reverse-proxy.conf the login never gets here: nginx sends /muma/api/auth/login
        // straight to MuMa. It still has to work here, because not every way in has that nginx in
        // front: lms.<domain> passes straight through to this server (docker-compose.yml), and so
        // do the test stack (docker/compose.test.yml) and the dev stack. Answering it locally is
        // what used to hand every user this server's own `api-key`; forwarding it is the only
        // answer that gives the same result on every route.
        const bool publicAuthPath{ isPublicAuthPath(pathInfo) };

        // A key opens nothing until it is verified: it must be this server's own `api-key` or a key
        // MuMa confirms, and otherwise a Subsonic u/p pair must hold. Any non-empty key used to be
        // accepted here, with the caller then named by the bare `u` parameter -- so any string plus
        // `u=<an admin>` was that admin on the routes below. See
        // docs/bug-reports/056-lms-any-key-is-admin.md.
        const AuthDecision auth{ authenticateRequest(request, publicAuthPath, session) };
        if (auth.outcome != AuthDecision::Outcome::Authenticated)
        {
            // Say "we could not check" rather than "you are not allowed", so the client keeps the
            // credentials it has and retries instead of logging the user out.
            if (auth.outcome == AuthDecision::Outcome::BackendUnavailable)
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

        const CallerRights rights{ resolveCallerRights(session, auth) };

        if (pathInfo == "/api/admin/libraries")
        {
            if (!mayAdministerServer(rights))
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
            if (!mayAdministerServer(rights))
            {
                response.setStatus(403);
                response.out() << "Forbidden";
                return;
            }

            std::string idStr = pathInfo.substr(21);
            db::MediaLibraryId id;
            try
            {
                id = db::MediaLibraryId{ std::stoll(idStr) };
            }
            catch (...)
            {
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
            if (!mayAdministerServer(rights))
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
                // until a new token is issued. A token shorter than /updateUser accepts
                // is refused with nothing changed.
                if (const auto problem{ replaceSubsonicToken(authTokenService, targetUser->getId(), token) })
                {
                    response.setStatus(400);
                    response.out() << *problem;
                    return;
                }

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
                for (size_t i = 0; i < encodedName.length(); ++i)
                {
                    if (encodedName[i] == '+')
                    {
                        encodedName.replace(i, 1, "%20");
                    }
                }
                std::string relativeUrl = "/api/artists/" + encodedName + "/image";

                // We use a promise/future to wait for the result in this simple implementation
                // Note: This blocks the current thread, but since images are small and MuMa is usually local, it's acceptable here
                struct ProxyResult
                {
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

                // This is a raw pass-through proxy: forward MuMa's real status verbatim
                // (e.g. 404 for a missing image) instead of collapsing it into a 502.
                getParams.treatAnyStatusAsSuccess = true;
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

                // Refused rather than queued: waiting here means holding an HTTP server thread, and
                // letting enough of these pile up is what used to take the whole pool and leave the
                // server answering nothing at all. See core::ConcurrencyGate.
                const auto mumaCallLease{ _mumaCallGate.tryAcquire() };
                if (!mumaCallLease)
                {
                    LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: artist image refused, " << _mumaCallGate.getInUseCount() << " of " << _mumaCallGate.getMaxConcurrent() << " calls to MuMa already in flight");
                    refuseAsBusy(response, "Too many requests to MuMa in flight");
                    return;
                }

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
            for (size_t i = 0; i < encodedPath.length(); ++i)
            {
                if (encodedPath[i] == '+')
                {
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

            // Raw pass-through proxy: forward MuMa's real status verbatim.
            postParams.treatAnyStatusAsSuccess = true;
            postParams.onSuccessFunc = [resultPromise](const Wt::Http::Message& msg) {
                resultPromise->set_value(msg.status());
            };
            postParams.onFailureFunc = [resultPromise]() {
                resultPromise->set_value(502);
            };

            // Refused rather than queued: waiting here means holding an HTTP server thread, and
            // letting enough of these pile up is what used to take the whole pool and leave the
            // server answering nothing at all. See core::ConcurrencyGate.
            const auto mumaCallLease{ _mumaCallGate.tryAcquire() };
            if (!mumaCallLease)
            {
                LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: track refresh refused, " << _mumaCallGate.getInUseCount() << " of " << _mumaCallGate.getMaxConcurrent() << " calls to MuMa already in flight");
                refuseAsBusy(response, "{\"status\":\"error\", \"detail\": \"Too many requests to MuMa in flight\"}");
                return;
            }

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

        const RouteFamily routeFamily{ classifyRouteFamily(pathInfo) };
        if (routeFamily == RouteFamily::Users)
        {
            if (pathInfo == "/users/sync")
            {
                // MuMa sends this with its system key whenever an account changes; a disabled or
                // demoted user's cached key verdict must not outlive that news.
                if (!mayTriggerUserSync(rights))
                {
                    response.setStatus(403);
                    response.out() << "Forbidden";
                    return;
                }
                _keyVerdictCache.clear();
                _userSynchronizer.syncUsers();
                response.out() << "{\"status\":\"ok\"}";
                return;
            }

            // A system key is a service, not a person: per-user settings need a verified user.
            if (!isUserCaller(rights))
            {
                response.setStatus(401);
                response.out() << "User not found";
                return;
            }
            // /users/{user_id}/settings/{app_id}
            if (const std::optional<UserSettingsPath> settingsPath{ parseUserSettingsPath(pathInfo) })
            {
                if (!settingsPath->mumaUserId)
                {
                    response.setStatus(400);
                    response.out() << "Invalid User ID";
                    return;
                }
                const db::UserId userId{ *settingsPath->mumaUserId };
                const std::string& appId{ settingsPath->appId };

                // The id is MuMa's (it is forwarded to MuMa's /api/users/{id}/settings unchanged), so it
                // is compared with the caller's MuMa id, not their LMS id.
                if (!mayAccessUserSettings(rights, userId.getValue()))
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

                    auto resultPromise = std::make_shared<std::promise<std::string>>();
                    auto resultFuture = resultPromise->get_future();

                    core::http::ClientGETRequestParameters getParams;
                    getParams.relativeUrl = "/api/users/" + std::to_string(userId.getValue()) + "/settings/" + appId;
                    if (!_mumaApiKey.empty())
                        getParams.headers.push_back(Wt::Http::Message::Header("X-API-Key", _mumaApiKey));

                    getParams.onSuccessFunc = [resultPromise](const Wt::Http::Message& msg) {
                        resultPromise->set_value(msg.body());
                    };
                    getParams.onFailureFunc = [resultPromise]() {
                        resultPromise->set_value("{\"settings\": null}");
                    };

                    // Refused rather than queued: waiting here means holding an HTTP server thread, and
                    // letting enough of these pile up is what used to take the whole pool and leave the
                    // server answering nothing at all. See core::ConcurrencyGate.
                    const auto mumaCallLease{ _mumaCallGate.tryAcquire() };
                    if (!mumaCallLease)
                    {
                        LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: settings read refused, " << _mumaCallGate.getInUseCount() << " of " << _mumaCallGate.getMaxConcurrent() << " calls to MuMa already in flight");
                        refuseAsBusy(response, "{\"settings\": null}");
                        return;
                    }

                    _httpClient->sendGETRequest(std::move(getParams));
                    if (resultFuture.wait_for(std::chrono::seconds(10)) == std::future_status::ready)
                    {
                        response.out() << resultFuture.get();
                    }
                    else
                    {
                        response.setStatus(504);
                    }
                }
                else if (request.method() == "POST")
                {
                    if (!_httpClient)
                    {
                        response.setStatus(500);
                        return;
                    }

                    std::string jsonStr((std::istreambuf_iterator<char>(request.in())), std::istreambuf_iterator<char>());

                    auto resultPromise = std::make_shared<std::promise<int>>();
                    auto resultFuture = resultPromise->get_future();

                    core::http::ClientPOSTRequestParameters postParams;
                    postParams.relativeUrl = "/api/users/" + std::to_string(userId.getValue()) + "/settings/" + appId;
                    if (!_mumaApiKey.empty())
                        postParams.message.addHeader("X-API-Key", _mumaApiKey);
                    postParams.message.addHeader("Content-Type", "application/json");
                    postParams.message.addBodyText(jsonStr);

                    // Raw pass-through proxy: forward MuMa's real status verbatim.
                    postParams.treatAnyStatusAsSuccess = true;
                    postParams.onSuccessFunc = [resultPromise](const Wt::Http::Message& msg) {
                        resultPromise->set_value(msg.status());
                    };
                    postParams.onFailureFunc = [resultPromise]() {
                        resultPromise->set_value(502);
                    };

                    // Refused rather than queued: waiting here means holding an HTTP server thread, and
                    // letting enough of these pile up is what used to take the whole pool and leave the
                    // server answering nothing at all. See core::ConcurrencyGate.
                    const auto mumaCallLease{ _mumaCallGate.tryAcquire() };
                    if (!mumaCallLease)
                    {
                        LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: settings write refused, " << _mumaCallGate.getInUseCount() << " of " << _mumaCallGate.getMaxConcurrent() << " calls to MuMa already in flight");
                        refuseAsBusy(response, "{\"status\":\"error\"}");
                        return;
                    }

                    _httpClient->sendPOSTRequest(std::move(postParams));
                    if (resultFuture.wait_for(std::chrono::seconds(10)) == std::future_status::ready)
                    {
                        response.setStatus(resultFuture.get());
                        response.out() << "{\"status\":\"ok\"}";
                    }
                    else
                    {
                        response.setStatus(504);
                    }
                }
            }
        }
        else if (routeFamily == RouteFamily::Api)
        {
            if (!_httpClient)
            {
                response.setStatus(500);
                response.out() << "Music Management not configured";
                return;
            }

            // Refused rather than queued: waiting here means holding an HTTP server thread, and
            // letting enough of these pile up is what used to take the whole pool and leave the
            // server answering nothing at all. See core::ConcurrencyGate.
            const auto mumaCallLease{ _mumaCallGate.tryAcquire() };
            if (!mumaCallLease)
            {
                LMS_LOG(API_SUBSONIC, WARNING, "MumaResource: generic proxy call refused, " << _mumaCallGate.getInUseCount() << " of " << _mumaCallGate.getMaxConcurrent() << " calls to MuMa already in flight");
                refuseAsBusy(response, "Too many requests to MuMa in flight");
                return;
            }

            // Generic proxy for all other /api/ calls. The content type travels with the
            // status and body because not every endpoint here answers JSON: a news
            // bulletin is an MP3, and a blob built from a response typed text/html is
            // one the browser's audio element refuses to play.
            auto resultPromise = std::make_shared<std::promise<GenericResult>>();
            auto resultFuture = resultPromise->get_future();
            // Only filled for a streamed response; every other call still reads msg.body().
            auto streamedBody = std::make_shared<std::string>();

            if (request.method() == "GET")
            {
                core::http::ClientGETRequestParameters getParams;
                // pathInfo comes back from Wt already decoded, so a name like "Silky Noize"
                // holds a real space. Put the encoding back before it goes on the wire, or
                // MuMa rejects the request line with a 400 without ever seeing the route.
                // The query string is still encoded and is appended untouched.
                getParams.relativeUrl = buildProxyRelativeUrl(pathInfo, request.queryString());

                if (isNewsBulletin(pathInfo))
                    collectResponseInChunks(getParams, streamedBody);

                // Only ever the CALLER's own key, so MuMa's RBAC judges the real caller. This used
                // to fall back to the configured system key when the caller sent no header, which
                // made `?apiKey=<anything>` reach MuMa as the system identity. A caller that
                // authenticated with u/p and no key reaches MuMa with no key, and MuMa answers
                // 401 for whatever needs one.
                // Who is really asking, as this server resolved it -- see forwardedClientAddress().
                for (auto& [name, value] : buildProxyHeaders({ .forwardKey = auth.forwardKey, .forwardedFor = forwardedClientAddress(request.clientAddress()), .contentType = {} }))
                    getParams.headers.emplace_back(std::move(name), std::move(value));

                // This is a raw pass-through proxy: MuMa's exact status code (401,
                // 403, 404, ...) and body are meaningful to the original caller and
                // must be forwarded verbatim, not collapsed into a generic 502.
                getParams.treatAnyStatusAsSuccess = true;
                getParams.onSuccessFunc = makeGenericSuccessHandler(resultPromise, streamedBody);
                getParams.onFailureFunc = [resultPromise]() {
                    resultPromise->set_value({ 502, std::string{}, "Bad Gateway" });
                };
                _httpClient->sendGETRequest(std::move(getParams));
            }
            else if (request.method() == "POST" || request.method() == "PUT" || request.method() == "DELETE" || request.method() == "PATCH")
            {
                core::http::ClientRequestWithBodyParameters bodyParams;
                // See the matching comment in the GET branch above: pathInfo is decoded.
                bodyParams.relativeUrl = buildProxyRelativeUrl(pathInfo, request.queryString());

                // See the matching comment in the GET branch above: the caller's own key only.
                // Who is really asking: the login on lms.<domain> reaches MuMa through here, and
                // MuMa's per-client login limit needs the client, not this server. See
                // forwardedClientAddress().
                for (const auto& [name, value] : buildProxyHeaders({ .forwardKey = auth.forwardKey, .forwardedFor = forwardedClientAddress(request.clientAddress()), .contentType = request.headerValue("Content-Type") }))
                    bodyParams.message.addHeader(name, value);

                std::string jsonStr((std::istreambuf_iterator<char>(request.in())), std::istreambuf_iterator<char>());
                bodyParams.message.addBodyText(jsonStr);

                // See the matching comment in the GET branch above: forward MuMa's
                // real status/body verbatim instead of collapsing it into a 502.
                bodyParams.treatAnyStatusAsSuccess = true;
                bodyParams.onSuccessFunc = [resultPromise](const Wt::Http::Message& msg) {
                    const std::string* responseType{ msg.getHeader("Content-Type") };
                    resultPromise->set_value({ msg.status(), responseType ? *responseType : std::string{}, msg.body() });
                };
                bodyParams.onFailureFunc = [resultPromise]() {
                    resultPromise->set_value({ 502, std::string{}, "Bad Gateway" });
                };

                // The verb travels with the request. Every PUT and DELETE used to leave here
                // as a POST, so MuMa answered 405 for a route that only takes the real verb
                // (editing or removing a radio channel) and the caller saw a method error
                // for a request it never sent.
                // PATCH too: MuMa's per-key account-settings write (bug report 116). It used to
                // fall through every branch here, send nothing, and then park this thread -- and
                // a MuMa call slot -- on a promise nobody would ever fulfil until the 30 s timeout.
                if (request.method() == "PUT")
                    _httpClient->sendPUTRequest(core::http::ClientPUTRequestParameters{ std::move(bodyParams) });
                else if (request.method() == "DELETE")
                    _httpClient->sendDELETERequest(core::http::ClientDELETERequestParameters{ std::move(bodyParams) });
                else if (request.method() == "PATCH")
                    _httpClient->sendPATCHRequest(core::http::ClientPATCHRequestParameters{ std::move(bodyParams) });
                else
                    _httpClient->sendPOSTRequest(core::http::ClientPOSTRequestParameters{ std::move(bodyParams) });
            }
            else
            {
                // A verb this proxy does not forward: say so at once rather than waiting out the
                // timeout below on a request that was never sent.
                response.setStatus(405);
                response.out() << "Method Not Allowed";
                return;
            }

            if (resultFuture.wait_for(std::chrono::seconds(30)) == std::future_status::ready)
            {
                auto res = resultFuture.get();
                response.setStatus(res.status);
                if (!res.contentType.empty())
                    response.setMimeType(res.contentType);
                response.out() << res.body;
            }
            else
            {
                response.setStatus(504);
                response.out() << "Gateway Timeout";
            }
            return;
        }
        else
        {
            response.setStatus(404);
        }
    }
} // namespace lms::api::muma
