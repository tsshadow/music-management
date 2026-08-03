/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <chrono>
#include <string>

#include <boost/asio/io_context.hpp>

#include "services/auth/IPasswordService.hpp"

#include "../PasswordServiceBase.hpp"

namespace lms::auth::musicManagement
{
    // How music-manager's answer maps onto a password check. Kept out of the class so it can be
    // tested without standing up an HTTP server: the mapping is where the damage was done.
    //
    // 200 -> the credentials are good.
    // 401/403 -> music-manager looked and said no. The only genuine failed attempt.
    // 429 -> music-manager's own per-account rate limit; it did not check the password.
    // anything else, or no answer at all -> we learned nothing about the password.
    PasswordCheckOutcome outcomeFromResponseStatus(int status);

    class MusicManagementPasswordService final : public PasswordServiceBase
    {
    public:
        MusicManagementPasswordService(boost::asio::io_context& ioContext, db::IDb& db, std::size_t maxThrottlerEntryCount);
        ~MusicManagementPasswordService();

    private:
        // IPasswordService
        PasswordCheckOutcome checkUserPassword(std::string_view loginName, std::string_view password) override;
        bool canSetPasswords() const override { return false; }
        PasswordAcceptabilityResult checkPasswordAcceptability(std::string_view password, const PasswordValidationContext& context) const override;
        void setPassword(db::UserId userId, std::string_view newPassword) override;

        std::string _apiUrl;
        std::string _apiKey;
        std::chrono::milliseconds _timeout;
    };
} // namespace lms::auth::musicManagement
