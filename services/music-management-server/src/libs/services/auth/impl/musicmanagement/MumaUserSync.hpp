/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <cstddef>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <vector>

namespace lms::db
{
    class Session;
}

namespace lms::auth::musicManagement
{
    /// One account as music-manager's `GET /api/users/` lists it.
    struct MumaAccount
    {
        int mumaId{};
        std::string username;
        bool isAdmin{};
        bool enabled{ true }; // a list without the `enabled` field predates it: every account was enabled
    };

    /// The parsed list. A row that cannot be used is left out and counted rather than failing the
    /// whole list: one malformed account must not keep every other account from being synced.
    struct MumaAccountList
    {
        std::vector<MumaAccount> accounts;
        /// Every MuMa id the list mentions, including rows rejected for another reason (a missing
        /// username, say). An id listed here is never treated as deleted.
        std::set<int> listedIds;
        std::size_t rejectedRows{};
        /// False when at least one row's id could not be read. Such a list cannot prove that any
        /// account is gone -- the unreadable row may be it -- so nothing is disabled as deleted.
        bool everyRowIdentified{ true };
    };

    /// Parses music-manager's user list. nullopt when the body is not a JSON array at all, in which
    /// case nothing may be concluded from it.
    std::optional<MumaAccountList> parseMumaAccounts(std::string_view body);

    /// What one synchronization changed.
    struct MumaSyncSummary
    {
        std::size_t created{};
        std::size_t updated{};
        std::size_t disabled{}; // newly disabled: disabled in MuMa, or gone from its list
        std::size_t reenabled{};
        std::size_t failed{}; // accounts whose database write failed and was skipped
    };

    /// Mirrors the listed accounts onto the LMS `user` table.
    ///
    /// - A listed account is matched by MuMa id, then case-insensitively by login name, and
    ///   created when neither finds a user. Its name, role and enabled state follow MuMa.
    /// - An account disabled in MuMa, or linked to a MuMa id the list no longer holds (deleted in
    ///   MuMa), is disabled here and loses every auth token. It is never deleted: listens,
    ///   ratings, stars and playlists refer to the user row by id and would be orphaned.
    /// - Users without a MuMa id are left alone: nothing proves they are MuMa accounts.
    ///
    /// Every account is written in its own transaction, so one failing write is logged and skipped
    /// instead of taking the rest of the sync with it. Must be called without a transaction open.
    MumaSyncSummary applyMumaAccounts(db::Session& session, const MumaAccountList& list);
} // namespace lms::auth::musicManagement
