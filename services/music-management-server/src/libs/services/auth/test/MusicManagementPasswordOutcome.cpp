/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include <boost/asio/ip/address.hpp>

#include "musicmanagement/MusicManagementPasswordService.hpp"

int main(int argc, char** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}

namespace lms::auth::musicManagement::tests
{
    // The whole point of the outcome enum is that these three answers stay apart. Collapsing any of
    // them into "wrong password" is what made a music-manager restart log every user out.

    TEST(MusicManagementPasswordOutcome, okIsAMatch)
    {
        EXPECT_EQ(outcomeFromResponseStatus(200), PasswordCheckOutcome::Match);
    }

    TEST(MusicManagementPasswordOutcome, unauthorizedIsTheOnlyRealMismatch)
    {
        EXPECT_EQ(outcomeFromResponseStatus(401), PasswordCheckOutcome::Mismatch);
        EXPECT_EQ(outcomeFromResponseStatus(403), PasswordCheckOutcome::Mismatch);
    }

    TEST(MusicManagementPasswordOutcome, rateLimitIsNotAMismatch)
    {
        // music-manager refused to check, so we know nothing about the password. Counting this as a
        // failed attempt would let one throttled account feed a second throttle on top of it.
        EXPECT_EQ(outcomeFromResponseStatus(429), PasswordCheckOutcome::Throttled);
    }

    TEST(MusicManagementPasswordOutcome, serverErrorsAreBackendErrors)
    {
        EXPECT_EQ(outcomeFromResponseStatus(500), PasswordCheckOutcome::BackendError);
        EXPECT_EQ(outcomeFromResponseStatus(502), PasswordCheckOutcome::BackendError);
        EXPECT_EQ(outcomeFromResponseStatus(503), PasswordCheckOutcome::BackendError);
        EXPECT_EQ(outcomeFromResponseStatus(504), PasswordCheckOutcome::BackendError);
    }

    TEST(MusicManagementPasswordOutcome, unexpectedStatusesAreNeverTreatedAsAMismatch)
    {
        // A redirect, a proxy error page or a 404 from a misconfigured URL all mean the check did
        // not happen. None of them may reach the user as "wrong username or password".
        for (const int status : { 0, 204, 301, 302, 400, 404, 418 })
            EXPECT_EQ(outcomeFromResponseStatus(status), PasswordCheckOutcome::BackendError) << "status " << status;
    }

    // music-manager rate limits failed logins per client address as well as per account. Every
    // check used to leave here without the client's address, so music-manager saw this server as
    // the only client there was (docs/bug-reports/079-google-login-unverified-email-and-lms-login-limit.md).

    TEST(MusicManagementLoginRequest, carriesTheClientAddressAsTheOnlyForwardedEntry)
    {
        const Wt::Http::Message message{ buildLoginRequest({ .loginName = "alice", .password = "secret", .apiKey = "system-key", .clientAddress = boost::asio::ip::make_address("203.0.113.7") }) };

        const std::string* forwarded{ message.getHeader("X-Forwarded-For") };
        ASSERT_NE(forwarded, nullptr);
        EXPECT_EQ(*forwarded, "203.0.113.7");

        std::size_t forwardedCount{};
        for (const Wt::Http::Message::Header& header : message.headers())
            forwardedCount += header.name() == "X-Forwarded-For" ? 1 : 0;
        EXPECT_EQ(forwardedCount, 1u);
    }

    TEST(MusicManagementLoginRequest, carriesAnIpv6ClientAddressUnbracketed)
    {
        const Wt::Http::Message message{ buildLoginRequest({ .loginName = "alice", .password = "secret", .apiKey = "", .clientAddress = boost::asio::ip::make_address("2001:db8::1") }) };

        const std::string* forwarded{ message.getHeader("X-Forwarded-For") };
        ASSERT_NE(forwarded, nullptr);
        EXPECT_EQ(*forwarded, "2001:db8::1");
    }

    TEST(MusicManagementLoginRequest, anUnknownClientAddsNoForwardedHeader)
    {
        // "Nobody said" must not turn into a claim that the client is 0.0.0.0: music-manager would
        // then put every such check into one bucket named after an address nobody has.
        const Wt::Http::Message message{ buildLoginRequest({ .loginName = "alice", .password = "secret", .apiKey = "system-key", .clientAddress = boost::asio::ip::address{} }) };

        EXPECT_EQ(message.getHeader("X-Forwarded-For"), nullptr);
    }

    TEST(MusicManagementLoginRequest, keepsTheKeyAndTheCredentials)
    {
        const Wt::Http::Message message{ buildLoginRequest({ .loginName = "alice", .password = "secret", .apiKey = "system-key", .clientAddress = boost::asio::ip::make_address("192.0.2.1") }) };

        const std::string* key{ message.getHeader("X-API-Key") };
        ASSERT_NE(key, nullptr);
        EXPECT_EQ(*key, "system-key");
        EXPECT_NE(message.body().find("\"username\""), std::string::npos);
        EXPECT_NE(message.body().find("alice"), std::string::npos);
    }
} // namespace lms::auth::musicManagement::tests
