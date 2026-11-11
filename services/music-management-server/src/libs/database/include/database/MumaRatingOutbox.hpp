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
#include <vector>

#include <Wt/WDateTime.h>

namespace lms::db
{
    class Session;
}

// The rating changes LMS still has to hand to music-manager, kept in lms.db so an outage of
// music-manager -- or a restart of LMS itself -- no longer loses them.
// docs/designs/lms-rating-outbox/technical.md.
//
// One row per user and rated item: only the last state of a rating matters, so a new change
// replaces the one still waiting. A plain table, not a Wt::Dbo object, like the listen outbox
// (MumaListenOutbox.hpp). Created by migration step 127 and, for a fresh database, by
// Session::createIndexesIfNeeded().
//
// Every function needs a transaction on `session`: a read transaction for the readers, a write
// transaction for the others.
namespace lms::db::mumaRatingOutbox
{
    // What a rating belongs to: the same triple music-manager stores it under.
    struct Key
    {
        std::string username;   // login name, as in the payload
        std::string objectType; // "track", "release" or "artist"
        std::string objectId;   // LMS track id, or the release or artist name

        bool operator==(const Key&) const = default;
    };

    // One rating change waiting to be relayed: the JSON body exactly as it will be POSTed.
    struct Entry
    {
        long long id{};
        Key key;
        std::string payload;
        Wt::WDateTime created;
        long long attempts{};
    };

    struct Status
    {
        std::size_t count{};
        std::optional<Wt::WDateTime> oldest; // when the oldest waiting change was queued; empty when none waits
    };

    // Queues the latest state of one rating and returns its id. A change still waiting for the
    // same key is removed first, and the new row gets a new, higher id: an answer that arrives
    // for the replaced row then removes nothing (docs/designs/lms-rating-outbox/technical.md).
    long long replace(Session& session, const Key& key, std::string_view payload, const Wt::WDateTime& created);

    // The oldest waiting change, if any.
    std::optional<Entry> front(Session& session);

    // Removes one change (delivered, or refused for good). Removing a change that is not there
    // any more is not an error.
    void remove(Session& session, long long id);

    // Counts one more failed delivery attempt for a change.
    void recordAttempt(Session& session, long long id);

    // Removes the oldest changes until at most `maxCount` remain; returns the keys that went.
    std::vector<Key> dropOverflow(Session& session, std::size_t maxCount);

    // Removes every change queued before `cutoff`; returns the keys that went.
    std::vector<Key> dropOlderThan(Session& session, const Wt::WDateTime& cutoff);

    Status getStatus(Session& session);
} // namespace lms::db::mumaRatingOutbox
