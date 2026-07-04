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
#include "database/objects/User.hpp"
#include "services/auth/IAuthTokenService.hpp"
#include "services/auth/IPasswordService.hpp"
#include "services/auth/IUserSynchronizer.hpp"

#include "ParameterParsing.hpp"
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
        bool mumaScrobblingEnabled{ getParameterAs<bool>(context.getParameters(), "mumaScrobblingEnabled").value_or(true) };

        {
            auto transaction{ context.getDbSession().createWriteTransaction() };
            if (User::find(context.getDbSession(), username))
                throw InternalErrorGenericError{ "User already exists" };

            User::pointer user{ context.getDbSession().create<User>(username) };
            user.modify()->setType(isAdmin ? UserType::ADMIN : UserType::REGULAR);
            user.modify()->setMumaScrobblingEnabled(mumaScrobblingEnabled);

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
        auto mumaScrobblingEnabled{ getParameterAs<bool>(context.getParameters(), "mumaScrobblingEnabled") };

        {
            auto transaction{ context.getDbSession().createWriteTransaction() };
            User::pointer user{ User::find(context.getDbSession(), username) };
            if (!user)
                throw RequestedDataNotFoundError{};

            if (isAdmin && context.getUser()->isAdmin())
                user.modify()->setType(*isAdmin ? UserType::ADMIN : UserType::REGULAR);

            if (mumaScrobblingEnabled)
                user.modify()->setMumaScrobblingEnabled(*mumaScrobblingEnabled);

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
