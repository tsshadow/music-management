/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include <optional>
#include <vector>

#include "core/ConcurrencyGate.hpp"

namespace lms::core::tests
{
    TEST(ConcurrencyGate, handsOutUpToItsLimit)
    {
        ConcurrencyGate gate{ 3 };

        std::vector<ConcurrencyGate::Lease> leases;
        for (std::size_t i{}; i < 3; ++i)
        {
            leases.push_back(gate.tryAcquire());
            EXPECT_TRUE(leases.back()) << "lease " << i;
        }

        EXPECT_EQ(gate.getInUseCount(), 3);
    }

    // The whole point: past the limit a caller is turned away rather than parked. A blocked caller
    // is holding an HTTP server thread, and there are only as many of those as there are cores.
    TEST(ConcurrencyGate, refusesRatherThanQueuing)
    {
        ConcurrencyGate gate{ 1 };

        const auto first{ gate.tryAcquire() };
        ASSERT_TRUE(first);

        const auto second{ gate.tryAcquire() };
        EXPECT_FALSE(second);
    }

    TEST(ConcurrencyGate, aLeaseFreesItsSlotWhenItGoesOutOfScope)
    {
        ConcurrencyGate gate{ 1 };

        {
            const auto lease{ gate.tryAcquire() };
            ASSERT_TRUE(lease);
            EXPECT_FALSE(gate.tryAcquire());
        }

        EXPECT_EQ(gate.getInUseCount(), 0);
        EXPECT_TRUE(gate.tryAcquire());
    }

    // A refused lease must not give a slot back when it is destroyed, or the gate would leak
    // capacity every time it turned someone away and stop limiting anything at all.
    TEST(ConcurrencyGate, arefusedLeaseReleasesNothing)
    {
        ConcurrencyGate gate{ 1 };

        const auto held{ gate.tryAcquire() };
        ASSERT_TRUE(held);

        {
            const auto refused{ gate.tryAcquire() };
            ASSERT_FALSE(refused);
        }

        EXPECT_EQ(gate.getInUseCount(), 1);
        EXPECT_FALSE(gate.tryAcquire());
    }

    TEST(ConcurrencyGate, aMovedLeaseReleasesExactlyOnce)
    {
        ConcurrencyGate gate{ 1 };

        {
            auto lease{ gate.tryAcquire() };
            ASSERT_TRUE(lease);

            std::optional<ConcurrencyGate::Lease> moved{ std::move(lease) };
            EXPECT_TRUE(*moved);
            EXPECT_EQ(gate.getInUseCount(), 1);
        }

        EXPECT_EQ(gate.getInUseCount(), 0);
    }

    // A limit of zero would turn the feature off by wedging it shut, which is the opposite of what
    // a caller passing a computed thread count expects from an accidental 0.
    TEST(ConcurrencyGate, alwaysAllowsAtLeastOne)
    {
        ConcurrencyGate gate{ 0 };

        EXPECT_TRUE(gate.tryAcquire());
    }
} // namespace lms::core::tests
