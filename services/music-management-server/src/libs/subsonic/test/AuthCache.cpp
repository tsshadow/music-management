/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include "AuthCache.hpp"

namespace lms::api::subsonic::tests
{
    namespace
    {
        using namespace std::chrono_literals;

        constexpr std::chrono::seconds grantedDuration{ 300 };
        constexpr std::chrono::seconds deniedDuration{ 30 };

        std::chrono::steady_clock::time_point epoch()
        {
            return std::chrono::steady_clock::time_point{};
        }
    } // namespace

    TEST(AuthCache, missOnAnUnknownKey)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 100 };

        EXPECT_FALSE(cache.lookup("key", epoch()).has_value());
    }

    TEST(AuthCache, grantedIsReturnedWithItsUserId)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 100 };
        cache.storeGranted("key", db::UserId{ 42 }, epoch());

        const auto entry{ cache.lookup("key", epoch() + 1s) };
        ASSERT_TRUE(entry.has_value());
        EXPECT_TRUE(entry->granted);
        EXPECT_EQ(entry->userId, db::UserId{ 42 });
    }

    // The point of the whole class: a client stuck on a stale API key must be answered from memory
    // instead of hitting the database, because every lookup there contends the process-wide lock.
    TEST(AuthCache, deniedIsRemembered)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 100 };
        cache.storeDenied("key", epoch());

        const auto entry{ cache.lookup("key", epoch() + 1s) };
        ASSERT_TRUE(entry.has_value());
        EXPECT_FALSE(entry->granted);
    }

    TEST(AuthCache, grantedAndDeniedExpireOnTheirOwnSchedules)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 100 };
        cache.storeGranted("granted", db::UserId{ 1 }, epoch());
        cache.storeDenied("denied", epoch());

        // A denial is held far more briefly than a grant: a key that was just provisioned has to
        // start working without the user waiting out a five minute grant window.
        EXPECT_TRUE(cache.lookup("granted", epoch() + deniedDuration + 1s).has_value());
        EXPECT_FALSE(cache.lookup("denied", epoch() + deniedDuration + 1s).has_value());

        EXPECT_FALSE(cache.lookup("granted", epoch() + grantedDuration + 1s).has_value());
    }

    TEST(AuthCache, aReStoreRefreshesTheExpiry)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 100 };
        cache.storeDenied("key", epoch());
        cache.storeDenied("key", epoch() + 20s);

        EXPECT_TRUE(cache.lookup("key", epoch() + 40s).has_value());
    }

    // Caching failures means an unauthenticated caller gets to put entries in this map. Without a
    // bound, someone sending a fresh random key on every request would grow it without limit.
    TEST(AuthCache, expiredEntriesAreReclaimedInsteadOfGrowing)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 4 };

        for (int i{}; i < 4; ++i)
            cache.storeDenied("key" + std::to_string(i), epoch());
        EXPECT_EQ(cache.getEntryCount(), 4);

        // Every one of those has expired by now, so the next store reclaims them all.
        cache.storeDenied("later", epoch() + deniedDuration + 1s);
        EXPECT_EQ(cache.getEntryCount(), 1);
    }

    TEST(AuthCache, entryCountNeverExceedsTheCap)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 4 };

        for (int i{}; i < 100; ++i)
            cache.storeDenied("key" + std::to_string(i), epoch());

        EXPECT_LE(cache.getEntryCount(), 4);
    }

    // Dropping a *grant* to make room for a denial would send an authenticated client back to the
    // database, which is exactly the load this cache exists to prevent.
    TEST(AuthCache, aFullCacheKeepsItsGrants)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 2 };
        cache.storeGranted("user1", db::UserId{ 1 }, epoch());
        cache.storeGranted("user2", db::UserId{ 2 }, epoch());

        cache.storeDenied("attacker", epoch());

        EXPECT_TRUE(cache.lookup("user1", epoch() + 1s).has_value());
        EXPECT_TRUE(cache.lookup("user2", epoch() + 1s).has_value());
        EXPECT_FALSE(cache.lookup("attacker", epoch() + 1s).has_value());
    }

    // A grant must still be storable when the cache is full of denials, otherwise a burst of bad
    // keys would lock real users out of the fast path for as long as it lasts.
    TEST(AuthCache, aGrantEvictsToMakeRoom)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 2 };
        cache.storeDenied("attacker1", epoch());
        cache.storeDenied("attacker2", epoch());

        cache.storeGranted("user", db::UserId{ 1 }, epoch());

        const auto entry{ cache.lookup("user", epoch() + 1s) };
        ASSERT_TRUE(entry.has_value());
        EXPECT_EQ(entry->userId, db::UserId{ 1 });
    }
    // Clearing is what a user sync triggers: an account disabled on music-manager must not be
    // served from a grant that is still inside its window.
    TEST(AuthCache, clearForgetsGrantsAndDenialsAlike)
    {
        AuthCache cache{ grantedDuration, deniedDuration, 100 };
        cache.storeGranted("granted", db::UserId{ 1 }, epoch());
        cache.storeDenied("denied", epoch());

        cache.clear();

        EXPECT_EQ(cache.getEntryCount(), 0);
        EXPECT_FALSE(cache.lookup("granted", epoch() + 1s).has_value());
        EXPECT_FALSE(cache.lookup("denied", epoch() + 1s).has_value());
    }
} // namespace lms::api::subsonic::tests
