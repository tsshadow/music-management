/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <Wt/Dbo/Dbo.h>
#include <gtest/gtest.h>

#include "database/MumaRatingOutbox.hpp"

#include "Common.hpp"

namespace lms::db::tests
{
    namespace
    {
        using mumaRatingOutbox::Key;

        const Key trackKey{ .username = "user", .objectType = "track", .objectId = "12" };
        const Key artistKey{ .username = "user", .objectType = "artist", .objectId = "Angerfist" };

        // The rating outbox table on its own, without the relay that drives it. Every test leaves
        // it empty again: the fixture checks that every table is empty afterwards.
        class MumaRatingOutboxTest : public DatabaseFixture
        {
        protected:
            void TearDown() override
            {
                auto transaction{ session.createWriteTransaction() };
                session.execute("DELETE FROM muma_rating_outbox");
            }

            long long replace(const Key& key, std::string_view payload, std::time_t created)
            {
                auto transaction{ session.createWriteTransaction() };
                return mumaRatingOutbox::replace(session, key, payload, Wt::WDateTime::fromTime_t(created));
            }

            std::optional<mumaRatingOutbox::Entry> front()
            {
                auto transaction{ session.createReadTransaction() };
                return mumaRatingOutbox::front(session);
            }

            mumaRatingOutbox::Status status()
            {
                auto transaction{ session.createReadTransaction() };
                return mumaRatingOutbox::getStatus(session);
            }
        };
    } // namespace

    // A fresh database starts at the current version and runs no migration step, so it gets the
    // table and its unique index from Session::createIndexesIfNeeded().
    TEST_F(MumaRatingOutboxTest, aFreshDatabaseHasTheTableAndItsUniqueIndex)
    {
        auto transaction{ session.createReadTransaction() };
        EXPECT_EQ(session.getDboSession()->query<int>("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'muma_rating_outbox'").resultValue(), 1);
        EXPECT_EQ(session.getDboSession()->query<int>("SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' AND name = 'muma_rating_outbox_item_idx'").resultValue(), 1);
    }

    TEST_F(MumaRatingOutboxTest, anEmptyOutboxHasNoFrontAndNoOldest)
    {
        EXPECT_FALSE(front());
        const mumaRatingOutbox::Status empty{ status() };
        EXPECT_EQ(empty.count, 0U);
        EXPECT_FALSE(empty.oldest);
    }

    TEST_F(MumaRatingOutboxTest, theFrontIsTheOldestChangeWithItsKeyAndPayload)
    {
        const long long first{ replace(trackKey, R"({"event":"rating_changed","rating":3})", 1'700'000'100) };
        const long long second{ replace(artistKey, R"({"event":"rating_changed","rating":5})", 1'700'000'300) };
        EXPECT_LT(first, second);

        const auto entry{ front() };
        ASSERT_TRUE(entry);
        EXPECT_EQ(entry->id, first);
        EXPECT_EQ(entry->key, trackKey);
        EXPECT_EQ(entry->payload, R"({"event":"rating_changed","rating":3})");
        EXPECT_EQ(entry->created.toTime_t(), 1'700'000'100);
        EXPECT_EQ(entry->attempts, 0);

        const mumaRatingOutbox::Status waiting{ status() };
        EXPECT_EQ(waiting.count, 2U);
        ASSERT_TRUE(waiting.oldest);
        EXPECT_EQ(waiting.oldest->toTime_t(), 1'700'000'100);
    }

    // The last state wins, and it gets a new, higher id: an answer still on its way for the
    // replaced row must not remove the new one.
    TEST_F(MumaRatingOutboxTest, aReplacedItemKeepsOneRowWithANewHigherId)
    {
        const long long first{ replace(trackKey, "rated 3", 1'700'000'000) };
        const long long other{ replace(artistKey, "rated 4", 1'700'000'001) };
        const long long second{ replace(trackKey, "rated 5", 1'700'000'002) };
        EXPECT_GT(second, other);
        EXPECT_GT(second, first);
        EXPECT_EQ(status().count, 2U);

        {
            auto transaction{ session.createWriteTransaction() };
            mumaRatingOutbox::remove(session, first);
        }
        EXPECT_EQ(status().count, 2U);
        EXPECT_EQ(front()->id, other);
        {
            auto transaction{ session.createWriteTransaction() };
            mumaRatingOutbox::remove(session, other);
        }
        const auto entry{ front() };
        ASSERT_TRUE(entry);
        EXPECT_EQ(entry->id, second);
        EXPECT_EQ(entry->payload, "rated 5");
    }

    TEST_F(MumaRatingOutboxTest, anotherUserOrTypeIsAnotherItem)
    {
        replace(trackKey, "a", 1'700'000'000);
        replace(Key{ .username = "other", .objectType = "track", .objectId = "12" }, "b", 1'700'000'001);
        replace(Key{ .username = "user", .objectType = "release", .objectId = "12" }, "c", 1'700'000'002);
        EXPECT_EQ(status().count, 3U);
    }

    TEST_F(MumaRatingOutboxTest, removingAMissingIdIsHarmless)
    {
        const long long id{ replace(trackKey, "a", 1'700'000'000) };
        {
            auto transaction{ session.createWriteTransaction() };
            mumaRatingOutbox::remove(session, id);
            EXPECT_NO_THROW(mumaRatingOutbox::remove(session, id));
            EXPECT_NO_THROW(mumaRatingOutbox::remove(session, id + 1000));
        }
        EXPECT_FALSE(front());
    }

    TEST_F(MumaRatingOutboxTest, attemptsAreCounted)
    {
        const long long id{ replace(trackKey, "a", 1'700'000'000) };
        {
            auto transaction{ session.createWriteTransaction() };
            mumaRatingOutbox::recordAttempt(session, id);
            mumaRatingOutbox::recordAttempt(session, id);
        }
        EXPECT_EQ(front()->attempts, 2);
    }

    TEST_F(MumaRatingOutboxTest, overflowDropsTheOldestFirstAndNamesThem)
    {
        for (int i{}; i < 5; ++i)
            replace(Key{ .username = "user", .objectType = "track", .objectId = std::to_string(i) }, std::to_string(i), 1'700'000'000 + i);

        std::vector<Key> dropped;
        {
            auto transaction{ session.createWriteTransaction() };
            dropped = mumaRatingOutbox::dropOverflow(session, 3);
            EXPECT_TRUE(mumaRatingOutbox::dropOverflow(session, 3).empty());
        }
        ASSERT_EQ(dropped.size(), 2U);
        EXPECT_EQ(dropped[0].objectId, "0");
        EXPECT_EQ(dropped[1].objectId, "1");
        EXPECT_EQ(status().count, 3U);
        EXPECT_EQ(front()->payload, "2");
    }

    TEST_F(MumaRatingOutboxTest, ageDropsOnlyWhatWasQueuedBeforeTheCutoffAndNamesIt)
    {
        replace(trackKey, "old", 1'700'000'000);
        replace(artistKey, "young", 1'700'000'500);

        std::vector<Key> dropped;
        {
            auto transaction{ session.createWriteTransaction() };
            dropped = mumaRatingOutbox::dropOlderThan(session, Wt::WDateTime::fromTime_t(1'700'000'500));
        }
        ASSERT_EQ(dropped.size(), 1U);
        EXPECT_EQ(dropped.front(), trackKey);
        EXPECT_EQ(status().count, 1U);
        EXPECT_EQ(front()->payload, "young");
    }
} // namespace lms::db::tests
