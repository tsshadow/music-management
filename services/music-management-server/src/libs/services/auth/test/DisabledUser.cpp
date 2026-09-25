/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <memory>
#include <string_view>

#include <boost/asio/ip/address.hpp>
#include <gtest/gtest.h>

#include "database/Session.hpp"
#include "database/objects/User.hpp"
#include "services/auth/IAuthTokenService.hpp"

#include "Common.hpp"
#include "PasswordServiceBase.hpp"

namespace lms::auth::tests
{
    namespace
    {
        // Accepts every password: what is under test is whether LMS still lets the user in.
        class AcceptingPasswordService final : public PasswordServiceBase
        {
        public:
            explicit AcceptingPasswordService(db::IDb& db)
                : PasswordServiceBase{ db, 10, /*useLoginThrottler*/ false }
            {
            }

        private:
            PasswordCheckOutcome checkUserPassword(std::string_view /*loginName*/, std::string_view /*password*/) override { return PasswordCheckOutcome::Match; }
            bool canSetPasswords() const override { return false; }
            PasswordAcceptabilityResult checkPasswordAcceptability(std::string_view /*password*/, const PasswordValidationContext& /*context*/) const override { return PasswordAcceptabilityResult::OK; }
            void setPassword(db::UserId /*userId*/, std::string_view /*newPassword*/) override {}
        };

        const boost::asio::ip::address clientAddress{ boost::asio::ip::make_address("192.0.2.1") };
    } // namespace

    // A user the MuMa synchronizer disabled keeps its data but gets in by no credential. The
    // synchronizer revokes its tokens; these tests cover what is left over -- a token issued after
    // that, and a password backend (internal, PAM) that knows nothing of MuMa.
    class DisabledUser : public db::tests::DatabaseFixture
    {
    protected:
        void disable(bool disabled = true)
        {
            auto transaction{ session.createWriteTransaction() };
            user.get().modify()->setDisabled(disabled);
        }

        db::tests::ScopedUser user{ session, "user" };
    };

    TEST_F(DisabledUser, aTokenOfADisabledUserOpensNothing)
    {
        const std::unique_ptr<IAuthTokenService> tokens{ createAuthTokenService(session.getDb(), 10) };
        tokens->registerDomain("subsonic", IAuthTokenService::DomainParameters{});
        tokens->createAuthToken("subsonic", user.getId(), "a-token-issued-before");

        EXPECT_EQ(tokens->processAuthToken("subsonic", clientAddress, "a-token-issued-before").state, IAuthTokenService::AuthTokenProcessResult::State::Granted);

        disable();
        EXPECT_EQ(tokens->processAuthToken("subsonic", clientAddress, "a-token-issued-before").state, IAuthTokenService::AuthTokenProcessResult::State::Denied);

        disable(false);
        EXPECT_EQ(tokens->processAuthToken("subsonic", clientAddress, "a-token-issued-before").state, IAuthTokenService::AuthTokenProcessResult::State::Granted);

        tokens->clearAuthTokens("subsonic", user.getId());
    }

    TEST_F(DisabledUser, aRightPasswordDoesNotLetADisabledUserIn)
    {
        AcceptingPasswordService service{ session.getDb() };
        IPasswordService& passwordService{ service };

        disable();
        const auto refused{ passwordService.checkUserPassword(clientAddress, "user", "secret") };
        EXPECT_EQ(refused.state, IPasswordService::CheckResult::State::Denied);

        disable(false);
        const auto granted{ passwordService.checkUserPassword(clientAddress, "user", "secret") };
        EXPECT_EQ(granted.state, IPasswordService::CheckResult::State::Granted);
        EXPECT_EQ(granted.userId, user.getId());
    }
} // namespace lms::auth::tests
