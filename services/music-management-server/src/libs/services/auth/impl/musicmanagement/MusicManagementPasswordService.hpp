/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <chrono>
#include <string>

#include <boost/asio/io_context.hpp>
#include <boost/asio/ip/address.hpp>

#include <Wt/Http/Message.h>

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

    // The POST /api/auth/login request for one password check, headers and body.
    //
    // It carries the address of the client that is logging in, as the only X-Forwarded-For entry:
    // music-manager counts failed logins per account *and* per client address, and without it every
    // check that reaches it through this server -- every Subsonic request on lms.<domain> -- came
    // from this server's own address. The value is the one this server resolved itself (the TCP
    // peer, or the address a trusted proxy reported when behind-reverse-proxy is on), never a
    // header the client sent, and music-manager only believes it because it comes from a trusted
    // network (services/music_manager/rate_limit.py). An unspecified address (the default, when
    // the caller did not say) adds no header.
    struct LoginRequestFields
    {
        std::string_view loginName;
        std::string_view password;
        std::string_view apiKey; // this server's key for music-manager; empty sends none
        boost::asio::ip::address clientAddress;
    };
    Wt::Http::Message buildLoginRequest(const LoginRequestFields& fields);

    class MusicManagementPasswordService final : public PasswordServiceBase
    {
    public:
        MusicManagementPasswordService(boost::asio::io_context& ioContext, db::IDb& db, std::size_t maxThrottlerEntryCount);
        ~MusicManagementPasswordService();

    private:
        // IPasswordService
        PasswordCheckOutcome checkUserPassword(std::string_view loginName, std::string_view password) override;
        PasswordCheckOutcome checkUserPasswordFrom(const boost::asio::ip::address& clientAddress, std::string_view loginName, std::string_view password) override;
        bool canSetPasswords() const override { return false; }
        PasswordAcceptabilityResult checkPasswordAcceptability(std::string_view password, const PasswordValidationContext& context) const override;
        void setPassword(db::UserId userId, std::string_view newPassword) override;

        std::string _apiUrl;
        std::string _apiKey;
        std::chrono::milliseconds _timeout;
    };
} // namespace lms::auth::musicManagement
