/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include "database/MumaListenOutbox.hpp"

#include "Common.hpp"

namespace lms::db::tests
{
    namespace
    {
        // The outbox table on its own, without the relay that drives it. Every test leaves it
        // empty again: the fixture checks that every table is empty afterwards.
        class MumaListenOutboxTest : public DatabaseFixture
        {
        protected:
            void TearDown() override
            {
                auto transaction{ session.createWriteTransaction() };
                session.execute("DELETE FROM muma_listen_outbox");
            }

            long long push(std::string_view payload, std::time_t created)
            {
                auto transaction{ session.createWriteTransaction() };
                return mumaListenOutbox::push(session, payload, Wt::WDateTime::fromTime_t(created));
            }

            std::optional<mumaListenOutbox::Entry> front()
            {
                auto transaction{ session.createReadTransaction() };
                return mumaListenOutbox::front(session);
            }

            mumaListenOutbox::Status status()
            {
                auto transaction{ session.createReadTransaction() };
                return mumaListenOutbox::getStatus(session);
            }
        };
    } // namespace

    TEST_F(MumaListenOutboxTest, anEmptyOutboxHasNoFrontAndNoOldest)
    {
        EXPECT_FALSE(front());
        const mumaListenOutbox::Status empty{ status() };
        EXPECT_EQ(empty.count, 0U);
        EXPECT_FALSE(empty.oldest);
    }

    TEST_F(MumaListenOutboxTest, theFrontIsTheOldestPushAndKeepsItsPayloadByteForByte)
    {
        const long long first{ push(R"({"listened_at":1700000000,"track_title":"Raise Your Fist"})", 1'700'000'100) };
        const long long second{ push(R"({"listened_at":1700000200})", 1'700'000'300) };
        EXPECT_LT(first, second);

        const auto entry{ front() };
        ASSERT_TRUE(entry);
        EXPECT_EQ(entry->id, first);
        EXPECT_EQ(entry->payload, R"({"listened_at":1700000000,"track_title":"Raise Your Fist"})");
        EXPECT_EQ(entry->created.toTime_t(), 1'700'000'100);
        EXPECT_EQ(entry->attempts, 0);

        const mumaListenOutbox::Status waiting{ status() };
        EXPECT_EQ(waiting.count, 2U);
        ASSERT_TRUE(waiting.oldest);
        EXPECT_EQ(waiting.oldest->toTime_t(), 1'700'000'100);
    }

    TEST_F(MumaListenOutboxTest, removingTheFrontExposesTheNextAndRemovingTwiceIsHarmless)
    {
        const long long first{ push("a", 1'700'000'000) };
        const long long second{ push("b", 1'700'000'001) };
        {
            auto transaction{ session.createWriteTransaction() };
            mumaListenOutbox::remove(session, first);
            EXPECT_NO_THROW(mumaListenOutbox::remove(session, first));
        }
        EXPECT_EQ(front()->id, second);
    }

    TEST_F(MumaListenOutboxTest, attemptsAreCounted)
    {
        const long long id{ push("a", 1'700'000'000) };
        {
            auto transaction{ session.createWriteTransaction() };
            mumaListenOutbox::recordAttempt(session, id);
            mumaListenOutbox::recordAttempt(session, id);
        }
        EXPECT_EQ(front()->attempts, 2);
    }

    TEST_F(MumaListenOutboxTest, overflowDropsTheOldestFirst)
    {
        for (int i{}; i < 5; ++i)
            push(std::to_string(i), 1'700'000'000 + i);

        std::size_t dropped{};
        {
            auto transaction{ session.createWriteTransaction() };
            dropped = mumaListenOutbox::dropOverflow(session, 3);
            EXPECT_EQ(mumaListenOutbox::dropOverflow(session, 3), 0U);
        }
        EXPECT_EQ(dropped, 2U);
        EXPECT_EQ(status().count, 3U);
        EXPECT_EQ(front()->payload, "2");
    }

    TEST_F(MumaListenOutboxTest, ageDropsOnlyWhatWasQueuedBeforeTheCutoff)
    {
        push("old", 1'700'000'000);
        push("young", 1'700'000'500);

        std::size_t dropped{};
        {
            auto transaction{ session.createWriteTransaction() };
            dropped = mumaListenOutbox::dropOlderThan(session, Wt::WDateTime::fromTime_t(1'700'000'500));
        }
        EXPECT_EQ(dropped, 1U);
        EXPECT_EQ(status().count, 1U);
        EXPECT_EQ(front()->payload, "young");
    }
} // namespace lms::db::tests
