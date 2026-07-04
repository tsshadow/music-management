/*
 * copyright (c) 2019 emeric poupon
 *
 * This file is part of LMS.
 *
 * LMS is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * LMS is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with LMS.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "SubsonicResource.hpp"

#include <atomic>
#include <unordered_map>

#include "core/EnumSet.hpp"
#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/ITraceLogger.hpp"
#include "core/LiteralString.hpp"
#include "core/Md5.hpp"
#include "core/Service.hpp"
#include "core/String.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/AuthToken.hpp"
#include "database/objects/User.hpp"
#include "services/auth/IAuthTokenService.hpp"
#include "services/auth/IPasswordService.hpp"

#include "ParameterParsing.hpp"
#include "RequestContext.hpp"
#include "SubsonicResponse.hpp"
#include "endpoints/AlbumSongLists.hpp"
#include "endpoints/Bookmarks.hpp"
#include "endpoints/Browsing.hpp"
#include "endpoints/Jukebox.hpp"
#include "endpoints/MediaAnnotation.hpp"
#include "endpoints/MediaLibraryScanning.hpp"
#include "endpoints/MediaRetrieval.hpp"
#include "endpoints/Playlists.hpp"
#include "endpoints/Podcast.hpp"
#include "endpoints/Searching.hpp"
#include "endpoints/Spotify.hpp"
#include "endpoints/System.hpp"
#include "endpoints/Transcoding.hpp"
#include "endpoints/UserManagement.hpp"

namespace lms::api::subsonic
{
    std::unique_ptr<Wt::WResource> createSubsonicResource(db::IDb& db)
    {
        return std::make_unique<SubsonicResource>(db);
    }

    namespace
    {
        std::string parameterMapToDebugString(const Wt::Http::ParameterMap& parameterMap)
        {
            constexpr std::string_view redactedStr{ "*REDACTED*" };
            auto redactValueIfNeeded = [redactedStr](const std::string& type, const std::string& value) -> std::string_view {
                if (type == "p" || type == "password" || type == "apiKey")
                    return redactedStr;

                return value;
            };

            std::string res;

            bool firstParameter{ true };
            for (const auto& [type, values] : parameterMap)
            {
                if (!firstParameter)
                    res += ", ";
                firstParameter = false;

                res += "{" + type + "=";
                if (values.size() == 1)
                {
                    res += redactValueIfNeeded(type, values.front());
                }
                else
                {
                    res += "{";
                    bool firstValue{ true };
                    for (const std::string& value : values)
                    {
                        if (!firstValue)
                            res += ',';
                        firstValue = false;

                        res += redactValueIfNeeded(type, value);
                    }
                    res += "}";
                }
                res += "}";
            }

            return res;
        }

        void checkUserTypeIsAllowed(const db::User::pointer& user, core::EnumSet<db::UserType> allowedUserTypes)
        {
            assert(user);
            if (!allowedUserTypes.contains(user->getType()))
                throw UserNotAuthorizedError{};
        }

        Response handleNotImplemented(RequestContext& /*context*/)
        {
            throw NotImplementedGenericError{};
        }

        enum class AuthenticationMode
        {
            Authenticated,
            Unauthenticated,
        };
        using RequestHandlerFunc = std::function<Response(RequestContext& context)>;
        struct RequestEntryPointInfo
        {
            RequestHandlerFunc func;
            AuthenticationMode authMode{ AuthenticationMode::Authenticated };
            core::EnumSet<db::UserType> allowedUserTypes{ db::UserType::DEMO, db::UserType::REGULAR, db::UserType::ADMIN };
        };

        const std::unordered_map<core::LiteralString, RequestEntryPointInfo, core::LiteralStringHash, core::LiteralStringEqual> requestEntryPoints{
            // System
            { "/ping", { handlePingRequest } },
            { "/getLicense", { handleGetLicenseRequest } },
            { "/getOpenSubsonicExtensions", { handleGetOpenSubsonicExtensions, AuthenticationMode::Unauthenticated } },

            // Browsing
            { "/getMusicFolders", { handleGetMusicFoldersRequest } },
            { "/getIndexes", { handleGetIndexesRequest } },
            { "/getMusicDirectory", { handleGetMusicDirectoryRequest } },
            { "/getGenres", { handleGetGenresRequest } },
            { "/getTags", { handleGetTagsRequest } },
            { "/getMoods", { handleGetMoodRequest } },
            { "/getYears", { handleGetYearsRequest } },
            { "/getArtists", { handleGetArtistsRequest } },
            { "/getArtistList", { handleGetArtistListRequest } },
            { "/getArtist", { handleGetArtistRequest } },
            { "/getAlbum", { handleGetAlbumRequest } },
            { "/getSong", { handleGetSongRequest } },
            { "/getSingles", { handleGetSinglesRequest } },
            { "/getVideos", { handleNotImplemented } },
            { "/getArtistInfo", { handleNotImplemented } },
            { "/getArtistInfo2", { handleGetArtistInfo2Request } },
            { "/getAlbumInfo", { handleGetAlbumInfo } },
            { "/getAlbumInfo2", { handleGetAlbumInfo2 } },
            { "/getSimilarSongs", { handleGetSimilarSongsRequest } },
            { "/getSimilarSongs2", { handleGetSimilarSongs2Request } },
            { "/getTopSongs", { handleGetTopSongs } },

            // Album/song lists
            { "/getAlbumList", { handleGetAlbumListRequest } },
            { "/getAlbumList2", { handleGetAlbumList2Request } },
            { "/getRandomSongs", { handleGetRandomSongsRequest } },
            { "/getSongsByGenre", { handleGetSongsByGenreRequest } },
            { "/getSongsByGenreAndYear", { handleGetSongsByGenreRequest } },
            { "/getSongs", { handleGetSongs } },
            { "/getSongSortMethods", { handleGetSongSortMethods } },
            { "/getLineups", { handleGetLineups } },
            { "/getNowPlaying", { handleGetNowPlayingRequest } },
            { "/getStarred", { handleGetStarredRequest } },
            { "/getStarred2", { handleGetStarred2Request } },

            // Searching
            { "/search", { handleNotImplemented } },
            { "/search2", { handleSearch2Request } },
            { "/search3", { handleSearch3Request } },

            // Playlists
            { "/getPlaylists", { handleGetPlaylistsRequest } },
            { "/getPlaylist", { handleGetPlaylistRequest } },
            { "/createPlaylist", { handleCreatePlaylistRequest } },
            { "/updatePlaylist", { handleUpdatePlaylistRequest } },
            { "/deletePlaylist", { handleDeletePlaylistRequest } },

            // Media retrieval
            { "/hls", { handleNotImplemented } },
            { "/getCaptions", { handleNotImplemented } },
            { "/getLyrics", { handleGetLyrics } },
            { "/getLyricsBySongId", { handleGetLyricsBySongId } },
            { "/getAvatar", { handleNotImplemented } },

            // Transcoding extensions
            { "/getTranscodeDecision", { handleGetTranscodeDecision } },

            // Media annotation
            { "/star", { handleStarRequest } },
            { "/unstar", { handleUnstarRequest } },
            { "/setRating", { handleSetRating } },
            { "/scrobble", { handleScrobble } },

            // Sharing
            { "/getShares", { handleNotImplemented } },
            { "/createShares", { handleNotImplemented } },
            { "/updateShare", { handleNotImplemented } },
            { "/deleteShare", { handleNotImplemented } },

            // Podcast
            { "/getPodcasts", { handleGetPodcasts } },
            { "/getNewestPodcasts", { handleGetNewestPodcasts } },
            { "/refreshPodcasts", { handleRefreshPodcasts, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/createPodcastChannel", { handleCreatePodcastChannel, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/deletePodcastChannel", { handleDeletePodcastChannel, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/deletePodcastEpisode", { handleDeletePodcastEpisode, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/downloadPodcastEpisode", { handleDownloadPodcastEpisode, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/getPodcastEpisode", { handleGetPodcastEpisode } },

            // Jukebox
            { "/jukeboxControl", { handleJukeboxControl } },

            // Spotify extensions
            { "/getSpotifyCuratedPlaylists", { handleGetSpotifyCuratedPlaylists } },
            { "/getSpotifyPlaylist", { handleGetSpotifyPlaylistRequest } },
            { "/getSpotifyTracks", { handleGetSpotifyTracks } },
            { "/getSpotifyHistory", { handleGetSpotifyHistory } },
            { "/spotifyImportFromListenBrainz", { handleSpotifyImportFromListenBrainz } },

            // Internet radio
            { "/getInternetRadioStations", { handleNotImplemented } },
            { "/createInternetRadioStation", { handleNotImplemented } },
            { "/updateInternetRadioStation", { handleNotImplemented } },
            { "/deleteInternetRadioStation", { handleNotImplemented } },

            // Chat
            { "/getChatMessages", { handleNotImplemented } },
            { "/addChatMessages", { handleNotImplemented } },

            // User management
            { "/getUser", { handleGetUserRequest } },
            { "/getUsers", { handleGetUsersRequest, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/createUser", { handleCreateUserRequest, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/updateUser", { handleUpdateUserRequest } },
            { "/deleteUser", { handleDeleteUserRequest, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/changePassword", { handleChangePassword } },

            // Bookmarks
            { "/getBookmarks", { handleGetBookmarks } },
            { "/createBookmark", { handleCreateBookmark } },
            { "/deleteBookmark", { handleDeleteBookmark } },
            { "/getPlayQueue", { handleGetPlayQueue } },
            { "/savePlayQueue", { handleSavePlayQueue } },
            { "/getPlayQueueByIndex", { handleGetPlayQueueByIndex } },
            { "/savePlayQueueByIndex", { handleSavePlayQueueByIndex } },

            // Media library scanning
            { "/getScanStatus", { Scan::handleGetScanStatus } },
            { "/startScan", { Scan::handleStartScan, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
            { "/updateScanSettings", { Scan::handleUpdateScanSettings, AuthenticationMode::Authenticated, { db::UserType::ADMIN } } },
        };

        using MediaRetrievalHandlerFunc = std::function<void(RequestContext&, const Wt::Http::Request&, Wt::Http::Response&)>;
        const std::unordered_map<core::LiteralString, MediaRetrievalHandlerFunc, core::LiteralStringHash, core::LiteralStringEqual> mediaRetrievalHandlers{
            // Media retrieval
            { "/download", handleDownload },
            { "/stream", handleStream },
            { "/getCoverArt", handleGetCoverArt },

            // Transcoding extension
            { "/getTranscodeStream", handleGetTranscodeStream },
        };

        struct TLSMonotonicMemoryResourceCleaner
        {
            TLSMonotonicMemoryResourceCleaner() = default;
            ~TLSMonotonicMemoryResourceCleaner()
            {
                TLSMonotonicMemoryResource::getInstance().reset();
            }

        private:
            TLSMonotonicMemoryResourceCleaner(const TLSMonotonicMemoryResourceCleaner&) = delete;
            TLSMonotonicMemoryResourceCleaner& operator=(const TLSMonotonicMemoryResourceCleaner&) = delete;
        };

        db::User::pointer getUserFromUserId(db::Session& session, db::UserId userId)
        {
            auto transaction{ session.createReadTransaction() };

            if (db::User::pointer user{ db::User::find(session, userId) })
                return user;

            throw UserNotAuthorizedError{};
        }
    } // namespace

    SubsonicResource::SubsonicResource(db::IDb& db)
        : _config{ readSubsonicResourceConfig(*core::Service<core::IConfig>::get()) }
        , _db{ db }
    {
    }

    void SubsonicResource::handleRequest(const Wt::Http::Request& request, Wt::Http::Response& response)
    {
        static std::atomic<std::size_t> curRequestId{};

        const std::size_t requestId{ curRequestId++ };
        TLSMonotonicMemoryResourceCleaner memoryResourceCleaner;

        constexpr std::string_view optionalSuffix{ ".view" };
        std::string requestPath{ request.pathInfo() };
        if (core::stringUtils::stringEndsWith(requestPath, optionalSuffix))
            requestPath.resize(requestPath.length() - optionalSuffix.size());

        LMS_LOG(API_SUBSONIC, DEBUG, "Handling request " << requestId << " to '" << requestPath << " with params = " << parameterMapToDebugString(request.getParameterMap()) << "', continuation = " << (request.continuation() ? "true" : "false"));

        try
        {
            if (!handleMediaRetrievalRequest(requestPath, request, response))
                handleRequest(requestPath, request, response);

            LMS_LOG(API_SUBSONIC, DEBUG, "Request " << requestId << " to '" << requestPath << "' handled!");
        }
        catch (const Error& e)
        {
            LMS_LOG(API_SUBSONIC, ERROR, "Error while processing request " << requestId << " to '" << requestPath << "' with params = " << parameterMapToDebugString(request.getParameterMap()) << ": code = " << static_cast<int>(e.getCode()) << ", msg = '" << e.getMessage() << "'");

            // Re-throw if it's already caught and handled partially or needs more handling
            // In the original HEAD there was specific writing code, but upstream changed the logging.
            // Let's see how upstream handles the response.
            // Looking at the rest of the file, handleRequest (the other one) also catches Error.

            // Wait, the original HEAD code was:
            /*
            Response resp{ Response::createFailedResponse(protocolVersion, e) };
            resp.write(response.out(), format);
            response.setMimeType(std::string{ ResponseFormatToMimeType(format) });
            */
            // But 'protocolVersion' and 'format' are not defined here in the upstream version of handleRequest (it's in the other handleRequest).
            // Upstream's handleRequest(const std::string& requestPath, ...) handles the response writing.

            // If I look at the context, this catch is inside SubsonicResource::handleRequest(const Wt::Http::Request& request, Wt::Http::Response& response)
            // It calls handleMediaRetrievalRequest or handleRequest(string, ...).
            // Both of those have their own try-catch for Error.

            // So if an Error is thrown and NOT caught by them, it ends up here.
            // Let's just use the upstream logging.
        }
    }

    bool SubsonicResource::handleMediaRetrievalRequest(const std::string& requestPath, const Wt::Http::Request& request, Wt::Http::Response& response)
    {
        auto itStreamHandler{ mediaRetrievalHandlers.find(requestPath) };
        if (itStreamHandler == mediaRetrievalHandlers.end())
            return false;

        LMS_SCOPED_TRACE_OVERVIEW("Subsonic", itStreamHandler->first);

        try
        {
            RequestContext requestContext{ request, _db.getTLSSession(), _config };

            // Media retrieval endpoints are always authenticated but we don't reauth user for a continuation
            db::User::pointer user;
            if (!request.continuation())
                user = getUserFromUserId(_db.getTLSSession(), authenticateUser(request));

            requestContext.setUser(user);

            itStreamHandler->second(requestContext, request, response);

            return true;
        }
        catch (const UserNotAuthorizedError&)
        {
            response.setStatus(401); // Unauthorized
            throw;
        }
        catch (const RequiredParameterMissingError&)
        {
            response.setStatus(400); // Bad Request
            throw;
        }
        catch (const BadParameterGenericError&)
        {
            response.setStatus(400); // Bad Request
            throw;
        }
        catch (const RequestedDataNotFoundError&)
        {
            response.setStatus(404); // Not Found
            throw;
        }
        catch (const InternalErrorGenericError&)
        {
            response.setStatus(500); // Internal Server Error
            throw;
        }
        catch (const Error&)
        {
            response.setStatus(400); // Assume bad request
            throw;
        }
    }

    void SubsonicResource::handleRequest(const std::string& requestPath, const Wt::Http::Request& request, Wt::Http::Response& response)
    {
        auto writeResponse{ [&](const Response& resp, ResponseFormat format) {
            LMS_SCOPED_TRACE_DETAILED("Subsonic", "WriteResponse");
            resp.write(response.out(), format);
            response.setMimeType(std::string{ ResponseFormatToMimeType(format) });
        } };

        std::optional<RequestContext> requestContext;
        try
        {
            requestContext.emplace(request, _db.getTLSSession(), _config);
        }
        catch (const Error& e)
        {
            writeResponse(Response::createFailedResponse(defaultServerProtocolVersion, e), ResponseFormat::xml);
            throw;
        }

        try
        {
            if (auto itEntryPoint{ requestEntryPoints.find(requestPath) }; itEntryPoint != requestEntryPoints.end())
            {
                LMS_SCOPED_TRACE_OVERVIEW("Subsonic", itEntryPoint->first);

                db::User::pointer user;
                if (itEntryPoint->second.authMode == AuthenticationMode::Authenticated)
                {
                    user = getUserFromUserId(_db.getTLSSession(), authenticateUser(request));
                    checkUserTypeIsAllowed(user, itEntryPoint->second.allowedUserTypes);
                    requestContext->setUser(user);
                }

                const Response resp{ [&] {
                    LMS_SCOPED_TRACE_DETAILED("Subsonic", "HandleRequest");
                    return itEntryPoint->second.func(*requestContext);
                }() };

                writeResponse(resp, requestContext->getResponseFormat());
                return;
            }
            // do not disclose unhandled commands for unauthenticated users
            authenticateUser(request);

            LMS_LOG(API_SUBSONIC, ERROR, "Unhandled command '" << requestPath << "'");
            throw UnknownEntryPointGenericError{};
        }
        catch (const Error& e)
        {
            Response resp{ Response::createFailedResponse(requestContext->getServerProtocolVersion(), e) };
            writeResponse(resp, requestContext->getResponseFormat());
            throw;
        }
    }

    db::UserId SubsonicResource::authenticateUser(const Wt::Http::Request& request)
    {
        const auto& parameters{ request.getParameterMap() };

        const auto user{ getParameterAs<std::string>(parameters, "u") };
        const auto password{ getParameterAs<std::string>(parameters, "p") };
        const auto token{ getParameterAs<std::string>(parameters, "t") };
        const auto salt{ getParameterAs<std::string>(parameters, "s") };
        const auto apiKey{ getParameterAs<std::string>(parameters, "apiKey") };

        if (!_config.supportUserPasswordAuthentication && (password || user || token || salt))
            throw ProvidedAuthenticationMechanismNotSupportedError{};

        if (user && !password && !token)
            throw RequiredParameterMissingError{ "p" }; // or t
        if (!user && (password || token))
            throw RequiredParameterMissingError{ "u" };
        if (token && !salt)
            throw RequiredParameterMissingError{ "s" };

        if (password && token)
            throw MultipleConflictingAuthenticationMechanismsProvidedError{};

        if (!apiKey && !password && !token)
            throw RequiredParameterMissingError{ "apiKey" };

        const auto clientAddress{ boost::asio::ip::make_address(request.clientAddress()) };

        const std::string cacheKey{ (user ? *user : "") + ":" + (password ? *password : "") + ":" + (token ? *token : "") + ":" + (salt ? *salt : "") + ":" + (apiKey ? *apiKey : "") + ":" + clientAddress.to_string() };
        {
            std::lock_guard lock{ _authCacheMutex };
            if (auto it{ _authCache.find(cacheKey) }; it != _authCache.end())
            {
                if (it->second.expiry > std::chrono::steady_clock::now())
                    return it->second.userId;
            }
        }

        auto onAuthSuccess{ [&](db::UserId userId) {
            std::lock_guard lock{ _authCacheMutex };

            static int cleanupCounter = 0;
            if (++cleanupCounter >= 100)
            {
                cleanupCounter = 0;
                auto now{ std::chrono::steady_clock::now() };
                for (auto it{ _authCache.begin() }; it != _authCache.end();)
                {
                    if (it->second.expiry <= now)
                        it = _authCache.erase(it);
                    else
                        ++it;
                }
            }

            _authCache[cacheKey] = { userId, std::chrono::steady_clock::now() + std::chrono::minutes{ 5 } };
            return userId;
        } };

        if (apiKey)
        {
            const auto authResult{ core::Service<auth::IAuthTokenService>::get()->processAuthToken("subsonic", clientAddress, *apiKey) };
            if (authResult.state == auth::IAuthTokenService::AuthTokenProcessResult::State::Granted)
                return onAuthSuccess(authResult.authTokenInfo->userId);

            if (authResult.state == auth::IAuthTokenService::AuthTokenProcessResult::State::Throttled)
                throw LoginThrottledGenericError{};

            throw InvalidAPIkeyError{};
        }

        if (user)
        {
            if (token && salt)
            {
                db::Session& session{ _db.getTLSSession() };
                auto transaction{ session.createReadTransaction() };
                if (const auto dbUser{ db::User::find(session, *user) })
                {
                    db::UserId userId{ dbUser->getId() };
                    bool authenticated{ false };
                    db::AuthToken::find(session, "subsonic", userId, [&](const db::AuthToken::pointer& authToken) {
                        if (authenticated)
                            return;

                        if (core::crypto::md5(authToken->getValue() + *salt) == *token)
                            authenticated = true;
                    });

                    if (authenticated)
                        return onAuthSuccess(userId);
                }
            }

            if (password)
            {
                const std::string decodedPassword{ decodePasswordIfNeeded(*password) };
                if (auto passwordService{ core::Service<auth::IPasswordService>::get() })
                {
                    const auto passwordResult{ passwordService->checkUserPassword(clientAddress, *user, decodedPassword) };
                    if (passwordResult.state == auth::IPasswordService::CheckResult::State::Granted)
                        return onAuthSuccess(passwordResult.userId);

                    if (passwordResult.state == auth::IPasswordService::CheckResult::State::Throttled)
                        throw LoginThrottledGenericError{};
                }

                // Fallback: check if the password is actually an API Key
                const auto authResult{ core::Service<auth::IAuthTokenService>::get()->processAuthToken("subsonic", clientAddress, decodedPassword) };
                if (authResult.state == auth::IAuthTokenService::AuthTokenProcessResult::State::Granted)
                {
                    const auto authenticatedUser{ getUserFromUserId(_db.getTLSSession(), authResult.authTokenInfo->userId) };
                    if (authenticatedUser->getLoginName() == *user)
                        return onAuthSuccess(authResult.authTokenInfo->userId);
                }
            }
        }

        throw WrongUsernameOrPasswordError{};

        throw InternalErrorGenericError{ "Cannot authenticate user" };
    }
} // namespace lms::api::subsonic
