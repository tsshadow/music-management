/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <cstdio>
#include <filesystem>

#include "Common.hpp"

#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/AuthToken.hpp"
#include "database/objects/User.hpp"

namespace lms::db::tests
{
    namespace
    {
        std::unique_ptr<IDb> openDb(const std::filesystem::path& path)
        {
            auto db{ createDb(path) };

            Session session{ *db };
            session.prepareTablesIfNeeded();
            session.migrateSchemaIfNeeded();
            session.createIndexesIfNeeded();

            return db;
        }
    } // namespace

    // Auth tokens used to be mapped into an in-memory database attached as "volatile", so every
    // restart of the server threw away every Subsonic API key that had been provisioned into it.
    // Clients could not tell that apart from a wrong key: they just kept retrying a key that would
    // never work again, forever.
    //
    // Dropping the IDb closes the last connection, which is what takes an in-memory database with
    // it. Reopening the same file is therefore the honest stand-in for a restart.
    TEST(AuthTokenPersistence, aTokenOutlivesTheProcessThatIssuedIt)
    {
        const std::filesystem::path dbFile{ std::tmpnam(nullptr) };
        ScopedFileDeleter fileDeleter{ dbFile };

        {
            auto db{ openDb(dbFile) };
            Session session{ *db };

            auto transaction{ session.createWriteTransaction() };

            const User::pointer user{ session.create<User>("someone") };
            session.create<AuthToken>("subsonic", "the-provisioned-key", Wt::WDateTime{}, std::nullopt, user);
        }

        {
            auto db{ openDb(dbFile) };
            Session session{ *db };

            auto transaction{ session.createReadTransaction() };

            const AuthToken::pointer token{ AuthToken::find(session, "subsonic", "the-provisioned-key") };
            ASSERT_TRUE(token) << "the key was thrown away when the server stopped";
            EXPECT_EQ(token->getUserId(), User::find(session, "someone")->getId());
        }
    }
} // namespace lms::db::tests
