/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

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
} // namespace lms::auth::musicManagement::tests
