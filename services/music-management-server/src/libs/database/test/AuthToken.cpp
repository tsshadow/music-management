/*
 * Copyright (C) 2024 Emeric Poupon
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

#include "Common.hpp"

#include "database/objects/AuthToken.hpp"

namespace lms::db::tests
{
    using ScopedAuthToken = ScopedEntity<db::AuthToken>;

    TEST_F(DatabaseFixture, AuthTokens)
    {
        ScopedUser user{ session, "MyUser" };

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(AuthToken::getCount(session), 0);
        }

        ScopedAuthToken token{ session, "myDomain", "foo", Wt::WDateTime{}, std::nullopt, user.lockAndGet() };

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(AuthToken::getCount(session), 1);
        }

        {
            auto transaction{ session.createWriteTransaction() };
            AuthToken::clearUserTokens(session, "nonExistingDomain", user.getId());
        }
    }

    // A token is found by (domain, value) alone, so the database refuses a second row with the
    // same pair: a duplicate used to make that lookup throw for every user holding it.
    TEST_F(DatabaseFixture, AuthToken_valueIsUniquePerDomain)
    {
        ScopedUser user1{ session, "User1" };
        ScopedUser user2{ session, "User2" };
        ScopedAuthToken token{ session, "subsonic", "same-token-value", Wt::WDateTime{}, std::nullopt, user1.lockAndGet() };

        const std::string user2Id{ std::to_string(user2.getId().getValue()) };
        {
            auto transaction{ session.createWriteTransaction() };
            EXPECT_ANY_THROW(session.execute("INSERT INTO auth_token (version, domain, value, use_count, user_id) VALUES (0, 'subsonic', 'same-token-value', 0, " + user2Id + ")"));
        }
        {
            // The same value in another domain is a different token.
            auto transaction{ session.createWriteTransaction() };
            EXPECT_NO_THROW(session.execute("INSERT INTO auth_token (version, domain, value, use_count, user_id) VALUES (0, 'ui', 'same-token-value', 0, " + user2Id + ")"));
            session.execute("DELETE FROM auth_token WHERE domain = 'ui'");
        }
        {
            auto transaction{ session.createReadTransaction() };
            const AuthToken::pointer found{ AuthToken::find(session, "subsonic", "same-token-value") };
            ASSERT_TRUE(found);
            EXPECT_EQ(found->getUserId(), user1.getId());
        }
    }
} // namespace lms::db::tests
