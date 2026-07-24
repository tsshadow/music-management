/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <boost/asio/io_context.hpp>
#include "services/auth/IPasswordService.hpp"
#include "../PasswordServiceBase.hpp"

namespace lms::core::http
{
    class IClient;
}

namespace lms::auth::musicManagement
{
    class MusicManagementPasswordService final : public PasswordServiceBase
    {
    public:
        MusicManagementPasswordService(boost::asio::io_context& ioContext, db::IDb& db, std::size_t maxThrottlerEntryCount);
        ~MusicManagementPasswordService();

    private:
        // IPasswordService
        bool checkUserPassword(std::string_view loginName, std::string_view password) override;
        bool canSetPasswords() const override { return false; }
        PasswordAcceptabilityResult checkPasswordAcceptability(std::string_view password, const PasswordValidationContext& context) const override;
        void setPassword(db::UserId userId, std::string_view newPassword) override;

        std::string _apiUrl;
        std::string _apiKey;
        std::unique_ptr<core::http::IClient> _client;
    };
} // namespace lms::auth::musicManagement
