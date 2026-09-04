#include "api/muma/PathEncoding.hpp"

#include <gtest/gtest.h>

namespace lms::api::muma::tests
{
    TEST(PathEncoding, leavesAPlainPathAlone)
    {
        EXPECT_EQ(encodeProxyPath("/api/curation/artists/Adele"), "/api/curation/artists/Adele");
    }

    TEST(PathEncoding, encodesASpaceAsPercentTwenty)
    {
        // The reported failure: Wt decodes %20 into a real space, and forwarding that
        // unencoded makes MuMa answer 400 Bad Request.
        EXPECT_EQ(encodeProxyPath("/api/curation/artists/Silky Noize"), "/api/curation/artists/Silky%20Noize");
    }

    TEST(PathEncoding, keepsSlashesAsSeparators)
    {
        EXPECT_EQ(encodeProxyPath("/api/curation/artists/Silky Noize/genres"), "/api/curation/artists/Silky%20Noize/genres");
    }

    TEST(PathEncoding, keepsUnreservedCharacters)
    {
        EXPECT_EQ(encodeProxyPath("/api/curation/labels/A-B_C.D~E"), "/api/curation/labels/A-B_C.D~E");
    }

    TEST(PathEncoding, encodesReservedCharactersThatWouldChangeTheUrl)
    {
        EXPECT_EQ(encodeProxyPath("/api/curation/artists/A&B?x#y"), "/api/curation/artists/A%26B%3Fx%23y");
    }

    TEST(PathEncoding, encodesAnAlreadyLiteralPercent)
    {
        // pathInfo is decoded, so a percent here is part of the name, not an escape.
        EXPECT_EQ(encodeProxyPath("/api/curation/artists/100%"), "/api/curation/artists/100%25");
    }

    TEST(PathEncoding, encodesNonAsciiBytes)
    {
        EXPECT_EQ(encodeProxyPath("/api/curation/artists/Sigur Rós"), "/api/curation/artists/Sigur%20R%C3%B3s");
    }

    TEST(PathEncoding, handlesAnEmptyPath)
    {
        EXPECT_EQ(encodeProxyPath(""), "");
    }
} // namespace lms::api::muma::tests

int main(int argc, char** argv)
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
