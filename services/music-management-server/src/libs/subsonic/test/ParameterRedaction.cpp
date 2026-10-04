/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 *
 * LMS is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * LMS is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with LMS.  If not, see <http://www.gnu.org/licenses/>.
 */

// The request log line must not show a credential. A client once sent a whole signed
// getCoverArt URL as the `id`, and the error line printed the user's token and salt from inside
// it (MuMa bug report 150).

#include <gtest/gtest.h>

#include "ParameterParsing.hpp"

namespace lms::api::subsonic
{
    TEST(ParameterRedaction, topLevelSecretsAreRedacted)
    {
        const Wt::Http::ParameterMap parameters{
            { "c", { "Ultrasonic" } },
            { "p", { "hunter2" } },
            { "s", { "salt123" } },
            { "t", { "token456" } },
            { "u", { "user" } },
        };

        EXPECT_EQ(parameterMapToDebugString(parameters), "{c=Ultrasonic}, {p=*REDACTED*}, {s=*REDACTED*}, {t=*REDACTED*}, {u=user}");
    }

    TEST(ParameterRedaction, credentialsInsideANestedUrlAreRedacted)
    {
        const Wt::Http::ParameterMap parameters{
            { "id", { "https://muma.example.org/rest/getCoverArt?id=art-824661-1786979739&size=512&u=user&t=token456&s=salt123&v=1" } },
        };

        EXPECT_EQ(parameterMapToDebugString(parameters),
                  "{id=https://muma.example.org/rest/getCoverArt?id=art-824661-1786979739&size=512&u=*REDACTED*&t=*REDACTED*&s=*REDACTED*&v=1}");
    }

    TEST(ParameterRedaction, percentEncodedCredentialsAreRedacted)
    {
        EXPECT_EQ(redactCredentialsInValue("x%3Fid%3D1%26t%3Dtoken456%26s%3Dsalt123%26v%3D1"),
                  "x%3Fid%3D1%26t%3D*REDACTED*%26s%3D*REDACTED*%26v%3D1");
    }

    TEST(ParameterRedaction, plainValuesAreUntouched)
    {
        EXPECT_EQ(redactCredentialsInValue("art-824661-1786979739"), "art-824661-1786979739");
        EXPECT_EQ(redactCredentialsInValue("Tiesto & Friends"), "Tiesto & Friends");
        EXPECT_EQ(redactCredentialsInValue("a?size=512&title=s"), "a?size=512&title=s");
    }
} // namespace lms::api::subsonic
