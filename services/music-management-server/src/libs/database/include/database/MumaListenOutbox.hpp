/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>

#include <Wt/WDateTime.h>

namespace lms::db
{
    class Session;
}

// The listens LMS still has to hand to music-manager, kept in lms.db so an outage of
// music-manager -- or a restart of LMS itself -- no longer loses them.
// docs/designs/lms-listen-outbox/technical.md.
//
// A plain table, not a Wt::Dbo object: nothing ever loads a row as an object, the relay only
// needs "the oldest one", "remove it" and "how many". The table is created by migration step
// 124 and, for a fresh database, by Session::createIndexesIfNeeded().
//
// Every function needs a transaction on `session`: a read transaction for the readers, a write
// transaction for the others.
namespace lms::db::mumaListenOutbox
{
    // One listen waiting to be relayed: the JSON body exactly as it will be POSTed, so a retry
    // sends the same bytes -- same start time, which is what music-manager deduplicates on.
    struct Entry
    {
        long long id{};
        std::string payload;
        Wt::WDateTime created;
        long long attempts{};
    };

    struct Status
    {
        std::size_t count{};
        std::optional<Wt::WDateTime> oldest; // when the oldest waiting listen was queued; empty when none waits
    };

    // Appends a listen to the back of the outbox and returns its id. Ids only grow, so id order
    // is relay order.
    long long push(Session& session, std::string_view payload, const Wt::WDateTime& created);

    // The oldest waiting listen, if any.
    std::optional<Entry> front(Session& session);

    // Removes one listen (delivered, or refused for good). Removing a listen that is not there
    // any more is not an error.
    void remove(Session& session, long long id);

    // Counts one more failed delivery attempt for a listen.
    void recordAttempt(Session& session, long long id);

    // Removes the oldest listens until at most `maxCount` remain; returns how many went.
    std::size_t dropOverflow(Session& session, std::size_t maxCount);

    // Removes every listen queued before `cutoff`; returns how many went.
    std::size_t dropOlderThan(Session& session, const Wt::WDateTime& cutoff);

    Status getStatus(Session& session);
} // namespace lms::db::mumaListenOutbox
