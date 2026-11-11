/*
 * Copyright (C) 2020 Emeric Poupon
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

#pragma once

#include <string_view>

#include <Wt/Dbo/Dbo.h>

namespace lms::db
{
    class Session;

    using Version = std::size_t;

    class VersionInfo
    {
    public:
        using pointer = Wt::Dbo::ptr<VersionInfo>;

        VersionInfo();

        static VersionInfo::pointer getOrCreate(Session& session);
        static VersionInfo::pointer get(Session& session);

        Version getVersion() const { return _version; }
        void setVersion(Version version) { _version = static_cast<int>(version); }

        template<class Action>
        void persist(Action& a)
        {
            Wt::Dbo::field(a, _version, "db_version");
        }

    private:
        int _version;
    };

    namespace Migration
    {
        bool doDbMigration(Session& session); // return true if migration was performed
        void applyCustomExtensions(Session& session);
        // Creates the case-insensitive unique index on user.login_name, or logs the login names
        // that differ only in case and skips it. Returns whether the index exists afterwards.
        bool createUserLoginNameUniqueIndexIfPossible(Session& session);

        // The outbox of listens still to be relayed to music-manager
        // (database/MumaListenOutbox.hpp). Shared by migration step 124 and by
        // Session::createIndexesIfNeeded() for a fresh database, so the two cannot drift.
        // `created` is Unix seconds; `attempts` counts failed deliveries, for the status only.
        inline constexpr std::string_view mumaListenOutboxTableDefinition{ "CREATE TABLE IF NOT EXISTS muma_listen_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL, created INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)" };

        // The outbox of rating changes still to be relayed to music-manager
        // (database/MumaRatingOutbox.hpp), one row per user and rated item. Shared by migration
        // step 127 and by Session::createIndexesIfNeeded() for a fresh database, like the listen
        // outbox above. `object_id` is the LMS track id, or the release or artist name.
        inline constexpr std::string_view mumaRatingOutboxTableDefinition{ "CREATE TABLE IF NOT EXISTS muma_rating_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, object_type TEXT NOT NULL, object_id TEXT NOT NULL, payload TEXT NOT NULL, created INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)" };
        // The key music-manager stores a rating under; a new change replaces the waiting one.
        inline constexpr std::string_view mumaRatingOutboxIndexDefinition{ "CREATE UNIQUE INDEX IF NOT EXISTS muma_rating_outbox_item_idx ON muma_rating_outbox (username, object_type, object_id)" };
    } // namespace Migration
} // namespace lms::db
