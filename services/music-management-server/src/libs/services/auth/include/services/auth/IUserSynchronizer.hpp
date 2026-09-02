/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <functional>
#include <memory>

#include "core/Service.hpp"

namespace boost::asio
{
    class io_context;
}

namespace lms::db
{
    class IDb;
}

namespace lms::auth
{
    class IUserSynchronizer
    {
    public:
        virtual ~IUserSynchronizer() = default;
        virtual void syncUsers() = 0;

        // Called on every sync, before anything else. A sync is music-manager saying "something
        // about the users changed" -- an account created, disabled, re-enabled -- and anything
        // that remembers an earlier answer about a user has to forget it now rather than when
        // its own timer says so. One subscriber; passing an empty function unsubscribes.
        virtual void setOnUsersSynced(std::function<void()> callback) = 0;
    };

    std::unique_ptr<IUserSynchronizer> createUserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db);
} // namespace lms::auth
