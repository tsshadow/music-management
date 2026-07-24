/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <memory>
#include <string>

#include <boost/asio/io_context.hpp>

#include "services/auth/IUserSynchronizer.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::core::http
{
    class IClient;
}

namespace lms::auth::musicManagement
{
    class UserSynchronizer final : public IUserSynchronizer
    {
    public:
        UserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db);
        ~UserSynchronizer();

        void syncUsers() override;

    private:
        boost::asio::io_context& _ioContext;
        db::IDb& _db;
        std::string _apiUrl;
        std::string _apiKey;
        std::unique_ptr<core::http::IClient> _client;
    };

    std::unique_ptr<IUserSynchronizer> createUserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db);

} // namespace lms::auth::musicManagement
