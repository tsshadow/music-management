/*
 * Copyright (C) 2025 Emeric Poupon
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

#include "UserManagement.hpp"

#include "core/Service.hpp"
#include "core/UUID.hpp"
#include "database/Session.hpp"
#include "database/objects/AuthToken.hpp"
#include "database/objects/User.hpp"
#include "services/auth/IAuthTokenService.hpp"
#include "services/auth/IPasswordService.hpp"
#include "services/auth/IUserSynchronizer.hpp"

#include "ParameterParsing.hpp"
#include "UserSettingsValidation.hpp"
#include "responses/User.hpp"

namespace lms::api::subsonic
{
    using namespace db;

    namespace
    {
        void checkUserIsMySelfOrAdmin(RequestContext& context, const std::string& username)
        {
            if (context.getUser()->getLoginName() != username && !context.getUser()->isAdmin())
                throw UserNotAuthorizedError{};
        }

        /// Reads the optional integer parameter \p name and converts it with \p convert.
        /// An absent parameter yields nullopt; a value \p convert rejects is a bad parameter,
        /// never a blind cast to an enum value that does not exist.
        template<typename T>
        std::optional<T> getEnumParameter(RequestContext& context, const std::string& name, std::optional<T> (*convert)(int))
        {
            const auto raw{ getParameterAs<int>(context.getParameters(), name) };
            if (!raw)
                return std::nullopt;

            const std::optional<T> value{ convert(*raw) };
            if (!value)
                throw BadParameterGenericError{ name, "unknown value " + std::to_string(*raw) };
            return value;
        }

        /// Parses the comma-separated uiInlineArtistRelationships list, refusing any entry
        /// that is not a known track artist link type.
        core::EnumSet<TrackArtistLinkType> parseInlineArtistRelationships(const std::string& value)
        {
            core::EnumSet<TrackArtistLinkType> artistLinkTypes;
            for (std::string_view relationship : core::stringUtils::splitString(value, ','))
            {
                const auto raw{ core::stringUtils::readAs<int>(relationship) };
                if (!raw)
                    continue;

                const auto linkType{ userSettings::toTrackArtistLinkType(*raw) };
                if (!linkType)
                    throw BadParameterGenericError{ "uiInlineArtistRelationships", "unknown value " + std::to_string(*raw) };
                artistLinkTypes.insert(*linkType);
            }
            return artistLinkTypes;
        }

        /// Refuses a transcoding bitrate the server does not offer; the setter asserts on one.
        void checkTranscodeBitrate(std::optional<int> bitrate)
        {
            if (bitrate && (*bitrate < 0 || !isAudioBitrateAllowed(static_cast<Bitrate>(*bitrate))))
                throw BadParameterGenericError{ "subsonicDefaultTranscodeBitrate", "unsupported bitrate" };
        }

        /// Refuses a subsonic token that is too short, or that another user already holds:
        /// tokens are unique per domain (auth_token_domain_value_unique_idx), and refusing it
        /// here beats failing the whole request at commit. An empty token means "clear".
        void checkSubsonicTokenIsUsable(Session& session, UserId userId, const std::string& token)
        {
            if (token.empty())
                return;

            if (!userSettings::isAcceptableSubsonicToken(token))
                throw BadParameterGenericError{ "subsonicToken", "must be at least " + std::to_string(userSettings::minSubsonicTokenLength) + " characters" };

            const AuthToken::pointer existingToken{ AuthToken::find(session, "subsonic", token) };
            if (existingToken && existingToken->getUserId() != userId)
                throw BadParameterGenericError{ "subsonicToken", "cannot be used, choose another one" };
        }

        /// Makes \p token the user's only subsonic token (an empty one clears them all), and
        /// leaves the stored token alone when it already is exactly that.
        void applySubsonicToken(UserId userId, const std::string& token)
        {
            auto& authTokenService{ *core::Service<auth::IAuthTokenService>::get() };
            if (token.empty())
            {
                authTokenService.clearAuthTokens("subsonic", userId);
                return;
            }

            bool hasMatchingToken{ false };
            bool hasNonMatchingToken{ false };
            authTokenService.visitAuthTokens("subsonic", userId, [&](const auth::IAuthTokenService::AuthTokenInfo&, std::string_view storedToken) {
                if (storedToken == token)
                    hasMatchingToken = true;
                else
                    hasNonMatchingToken = true;
            });

            if (!hasMatchingToken || hasNonMatchingToken)
            {
                authTokenService.clearAuthTokens("subsonic", userId);
                authTokenService.createAuthToken("subsonic", userId, token);
            }
        }
    } // namespace

    Response handleGetUserRequest(RequestContext& context)
    {
        std::string username{ getMandatoryParameterAs<std::string>(context.getParameters(), "username") };

        auto transaction{ context.getDbSession().createReadTransaction() };

        checkUserIsMySelfOrAdmin(context, username);

        const User::pointer user{ User::find(context.getDbSession(), username) };
        if (!user)
            throw RequestedDataNotFoundError{};

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        response.addNode("user", createUserNode(context, user));

        return response;
    }

    Response handleGetUsersRequest(RequestContext& context)
    {
        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        Response::Node& usersNode{ response.createNode("users") };

        auto transaction{ context.getDbSession().createReadTransaction() };
        User::find(context.getDbSession(), User::FindParameters{}, [&](const User::pointer& user) {
            usersNode.addArrayChild("user", createUserNode(context, user));
        });

        return response;
    }

    Response handleCreateUserRequest(RequestContext& context)
    {
        std::string username{ getMandatoryParameterAs<std::string>(context.getParameters(), "username") };
        std::string password{ getMandatoryParameterAs<std::string>(context.getParameters(), "password") };
        bool isAdmin{ getParameterAs<bool>(context.getParameters(), "adminRole").value_or(false) };

        {
            auto transaction{ context.getDbSession().createWriteTransaction() };
            if (User::find(context.getDbSession(), username))
                throw InternalErrorGenericError{ "User already exists" };

            User::pointer user{ context.getDbSession().create<User>(username) };
            user.modify()->setType(isAdmin ? UserType::ADMIN : UserType::REGULAR);

            if (auto* passwordService{ core::Service<auth::IPasswordService>::get() })
                passwordService->setPassword(user->getId(), password);
        }

        return Response::createOkResponse(context.getServerProtocolVersion());
    }

    Response handleUpdateUserRequest(RequestContext& context)
    {
        std::string username{ getMandatoryParameterAs<std::string>(context.getParameters(), "username") };
        checkUserIsMySelfOrAdmin(context, username);

        auto password{ getParameterAs<std::string>(context.getParameters(), "password") };
        auto isAdmin{ getParameterAs<bool>(context.getParameters(), "adminRole") };

        auto subsonicEnableTranscodingByDefault{ getParameterAs<bool>(context.getParameters(), "subsonicEnableTranscodingByDefault") };
        // Every enum-valued setting is range-checked before anything is written: the feedback
        // and scrobbling backends are later used as keys into a map of backend instances, and
        // an unknown key there used to take the whole server down.
        auto subsonicDefaultTranscodeFormat{ getEnumParameter(context, "subsonicDefaultTranscodeFormat", &userSettings::toTranscodingOutputFormat) };
        auto subsonicDefaultTranscodeBitrate{ getParameterAs<int>(context.getParameters(), "subsonicDefaultTranscodeBitrate") };
        auto subsonicArtistListMode{ getEnumParameter(context, "subsonicArtistListMode", &userSettings::toSubsonicArtistListMode) };
        auto uiArtistReleaseSortMethod{ getEnumParameter(context, "uiArtistReleaseSortMethod", &userSettings::toReleaseSortMethod) };
        auto uiEnableInlineArtistRelationships{ getParameterAs<bool>(context.getParameters(), "uiEnableInlineArtistRelationships") };
        auto uiInlineArtistRelationships{ getParameterAs<std::string>(context.getParameters(), "uiInlineArtistRelationships") };
        auto feedbackBackend{ getEnumParameter(context, "feedbackBackend", &userSettings::toFeedbackBackend) };
        auto scrobblingBackend{ getEnumParameter(context, "scrobblingBackend", &userSettings::toScrobblingBackend) };
        auto listenbrainzToken{ getParameterAs<std::string>(context.getParameters(), "listenbrainzToken") };
        auto subsonicToken{ getParameterAs<std::string>(context.getParameters(), "subsonicToken") };

        checkTranscodeBitrate(subsonicDefaultTranscodeBitrate);

        std::optional<core::EnumSet<TrackArtistLinkType>> inlineArtistLinkTypes;
        if (uiInlineArtistRelationships)
            inlineArtistLinkTypes = parseInlineArtistRelationships(*uiInlineArtistRelationships);

        {
            auto transaction{ context.getDbSession().createWriteTransaction() };
            User::pointer user{ User::find(context.getDbSession(), username) };
            if (!user)
                throw RequestedDataNotFoundError{};

            // Checked before anything is modified.
            if (subsonicToken)
                checkSubsonicTokenIsUsable(context.getDbSession(), user->getId(), *subsonicToken);

            if (isAdmin && context.getUser()->isAdmin())
                user.modify()->setType(*isAdmin ? UserType::ADMIN : UserType::REGULAR);

            if (subsonicEnableTranscodingByDefault)
                user.modify()->setSubsonicEnableTranscodingByDefault(*subsonicEnableTranscodingByDefault);
            if (subsonicDefaultTranscodeFormat)
                user.modify()->setSubsonicDefaultTranscodingOutputFormat(*subsonicDefaultTranscodeFormat);
            if (subsonicDefaultTranscodeBitrate)
                user.modify()->setSubsonicDefaultTranscodingOutputBitrate(static_cast<Bitrate>(*subsonicDefaultTranscodeBitrate));
            if (subsonicArtistListMode)
                user.modify()->setSubsonicArtistListMode(*subsonicArtistListMode);
            if (uiArtistReleaseSortMethod)
                user.modify()->setUIArtistReleaseSortMethod(*uiArtistReleaseSortMethod);
            if (uiEnableInlineArtistRelationships)
                user.modify()->setUIEnableInlineArtistRelationships(*uiEnableInlineArtistRelationships);

            if (inlineArtistLinkTypes)
                user.modify()->setUIInlineArtistRelationships(*inlineArtistLinkTypes);

            if (feedbackBackend)
                user.modify()->setFeedbackBackend(*feedbackBackend);
            if (scrobblingBackend)
                user.modify()->setScrobblingBackend(*scrobblingBackend);
            if (listenbrainzToken)
                user.modify()->setListenBrainzToken(*listenbrainzToken);

            if (subsonicToken)
                applySubsonicToken(user->getId(), *subsonicToken);

            if (password)
            {
                if (auto* passwordService{ core::Service<auth::IPasswordService>::get() })
                {
                    passwordService->setPassword(user->getId(), *password);
                    core::Service<auth::IAuthTokenService>::get()->clearAuthTokens("ui", user->getId());
                }
            }
        }

        return Response::createOkResponse(context.getServerProtocolVersion());
    }

    Response handleDeleteUserRequest(RequestContext& context)
    {
        std::string username{ getMandatoryParameterAs<std::string>(context.getParameters(), "username") };

        {
            auto transaction{ context.getDbSession().createWriteTransaction() };
            User::pointer user{ User::find(context.getDbSession(), username) };
            if (!user)
                throw RequestedDataNotFoundError{};

            if (user->getId() == context.getUser()->getId())
                throw InternalErrorGenericError{ "Cannot delete yourself" };

            user.remove();
        }

        return Response::createOkResponse(context.getServerProtocolVersion());
    }

    Response handleChangePassword(RequestContext& context)
    {
        std::string password{ getMandatoryParameterAs<std::string>(context.getParameters(), "password") };

        {
            auto transaction{ context.getDbSession().createWriteTransaction() };
            User::pointer user{ User::find(context.getDbSession(), context.getUser()->getId()) };
            if (!user)
                throw RequestedDataNotFoundError{};

            if (auto* passwordService{ core::Service<auth::IPasswordService>::get() })
            {
                passwordService->setPassword(user->getId(), password);
                core::Service<auth::IAuthTokenService>::get()->clearAuthTokens("ui", user->getId());
            }
        }

        return Response::createOkResponse(context.getServerProtocolVersion());
    }

    Response handleSyncUsersRequest(RequestContext& context)
    {
        if (!context.getUser()->isAdmin())
            throw UserNotAuthorizedError{};

        if (auto* userSynchronizer{ core::Service<auth::IUserSynchronizer>::get() })
            userSynchronizer->syncUsers();

        return Response::createOkResponse(context.getServerProtocolVersion());
    }
} // namespace lms::api::subsonic
