/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#pragma once

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
    };

    std::unique_ptr<IUserSynchronizer> createUserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db);
} // namespace lms::auth
