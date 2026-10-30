/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <string_view>

#include <boost/asio/ip/address.hpp>
#include <gtest/gtest.h>

#include "database/Session.hpp"
#include "database/objects/User.hpp"

#include "Common.hpp"
#include "PasswordServiceBase.hpp"

namespace lms::auth::tests
{
    namespace
    {
        // A backend that accepts every password, the way music-manager accepts "User" for the
        // account "user": its users table compares login names case-insensitively. What is under
        // test is what LMS does with the name afterwards, not the password check itself.
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
    } // namespace

    class CaseInsensitiveLogin : public db::tests::DatabaseFixture
    {
    };

    // A login typed as "User" for the account "user" used to make LMS create a second, empty user
    // named "User": music-manager said yes, and getOrCreateUser() looked the typed name up exactly.
    // Every listen, rating and star from that session then belonged to the fork, and the listens
    // were relayed to music-manager under the fork's spelling
    // (docs/bug-reports/074-login-case-forks-user-identity.md).
    TEST_F(CaseInsensitiveLogin, aCaseVariantLoginSignsIntoTheExistingUser)
    {
        db::tests::ScopedUser existing{ session, "user" };

        AcceptingPasswordService service{ session.getDb() };
        IPasswordService& passwordService{ service };

        const auto result{ passwordService.checkUserPassword(boost::asio::ip::make_address("192.0.2.1"), "User", "secret") };

        ASSERT_EQ(result.state, IPasswordService::CheckResult::State::Granted);
        EXPECT_EQ(result.userId, existing.getId());

        auto transaction{ session.createReadTransaction() };
        EXPECT_EQ(db::User::getCount(session), 1U);
        EXPECT_EQ(db::User::find(session, existing.getId())->getLoginName(), "user");
    }

    // The shape production is in after the bug: the MuMa-linked account and a fork differing only
    // in case. A login with the fork's exact spelling must land on the linked account, and must not
    // throw on the lookup finding two rows.
    TEST_F(CaseInsensitiveLogin, anExistingForkNoLongerReceivesTheLogin)
    {
        // The schema refuses a new fork; a database the unique index could not be added to
        // (migrateFromV123 skips it while a fork exists) is what this covers.
        db::tests::ScopedNoLoginNameUniqueIndex noUniqueIndex{ session };
        db::tests::ScopedUser canonical{ session, "user" };
        db::tests::ScopedUser fork{ session, "User" };
        {
            auto transaction{ session.createWriteTransaction() };
            canonical.get().modify()->setMumaId(1);
        }

        AcceptingPasswordService service{ session.getDb() };
        IPasswordService& passwordService{ service };

        const auto result{ passwordService.checkUserPassword(boost::asio::ip::make_address("192.0.2.1"), "User", "secret") };

        ASSERT_EQ(result.state, IPasswordService::CheckResult::State::Granted);
        EXPECT_EQ(result.userId, canonical.getId());

        auto transaction{ session.createReadTransaction() };
        EXPECT_EQ(db::User::getCount(session), 2U);
    }
} // namespace lms::auth::tests
