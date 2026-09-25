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

namespace lms::db::tests
{
    TEST_F(DatabaseFixture, User)
    {
        {
            auto transaction{ session.createReadTransaction() };

            bool visited{};
            User::find(session, User::FindParameters{}, [&](const User::pointer&) {
                visited = true;
            });
            EXPECT_FALSE(visited);
        }

        ScopedUser user1{ session, "MyUser1" };
        ScopedUser user2{ session, "MyUser2" };

        {
            auto transaction{ session.createReadTransaction() };

            std::vector<UserId> visitedUsers;
            User::find(session, User::FindParameters{}, [&](const User::pointer& user) {
                visitedUsers.push_back(user->getId());
            });
            EXPECT_EQ(visitedUsers.size(), 2);
            EXPECT_EQ(visitedUsers[0], user1->getId());
            EXPECT_EQ(visitedUsers[1], user2->getId());
        }
    }

    // One account, whatever case its login name is typed in. music-manager accepts "Teun" for the
    // account "user"; an exact match here found nobody, and the authentication path created a
    // second user for the same person (docs/bug-reports/074-login-case-forks-user-identity.md).
    TEST_F(DatabaseFixture, User_findByLoginNameIgnoresCase)
    {
        ScopedUser user{ session, "user" };

        auto transaction{ session.createReadTransaction() };

        const User::pointer typedCapitalised{ User::find(session, std::string_view{ "Teun" }) };
        ASSERT_TRUE(typedCapitalised);
        EXPECT_EQ(typedCapitalised->getId(), user.getId());

        const User::pointer typedUpper{ User::find(session, std::string_view{ "TEUN" }) };
        ASSERT_TRUE(typedUpper);
        EXPECT_EQ(typedUpper->getId(), user.getId());

        EXPECT_FALSE(User::find(session, std::string_view{ "teun2" }));
    }

    // Where the bug already left two case variants behind, the lookup must not throw (more than one
    // row) and must land on the account music-manager knows about, even for the fork's exact spelling.
    TEST_F(DatabaseFixture, User_findByLoginNamePrefersTheMumaLinkedVariant)
    {
        ScopedUser canonical{ session, "user" };
        ScopedUser fork{ session, "Teun" };
        {
            auto transaction{ session.createWriteTransaction() };
            canonical.get().modify()->setMumaId(1);
        }

        auto transaction{ session.createReadTransaction() };

        const User::pointer found{ User::find(session, std::string_view{ "Teun" }) };
        ASSERT_TRUE(found);
        EXPECT_EQ(found->getId(), canonical.getId());
        EXPECT_NE(found->getId(), fork.getId());
    }
} // namespace lms::db::tests
