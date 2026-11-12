/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <memory>
#include <string_view>

#include <gtest/gtest.h>

#include "database/Session.hpp"
#include "database/objects/AuthToken.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"
#include "services/auth/IAuthTokenService.hpp"

#include "Common.hpp"
#include "musicmanagement/MumaUserSync.hpp"

namespace lms::auth::musicManagement::tests
{
    namespace
    {
        MumaAccountList parse(std::string_view body)
        {
            std::optional<MumaAccountList> list{ parseMumaAccounts(body) };
            EXPECT_TRUE(list.has_value()) << body;
            return list.value_or(MumaAccountList{});
        }
    } // namespace

    // What the synchronizer does with music-manager's GET /api/users/ answer, against a real
    // database. The HTTP round trip itself is not here: it is one GET whose body is handed to
    // parseMumaAccounts() and applyMumaAccounts() unchanged.
    class MumaUserSync : public db::tests::DatabaseFixture
    {
    protected:
        void SetUp() override
        {
            tokens = createAuthTokenService(session.getDb(), 10);
            tokens->registerDomain("subsonic", IAuthTokenService::DomainParameters{});
            tokens->registerDomain("ui", IAuthTokenService::DomainParameters{});
        }

        // Users the sync created are not scoped: they go here, with whatever else is left.
        void TearDown() override
        {
            auto transaction{ session.createWriteTransaction() };
            session.execute("DELETE FROM auth_token");
            session.execute("DELETE FROM rated_track");
            session.execute("DELETE FROM user");
        }

        MumaSyncSummary sync(std::string_view body) { return applyMumaAccounts(session, parse(body)); }

        db::User::pointer findByMumaId(int mumaId)
        {
            auto transaction{ session.createReadTransaction() };
            return db::User::findByMumaId(session, mumaId);
        }

        db::User::pointer findById(db::UserId userId)
        {
            auto transaction{ session.createReadTransaction() };
            return db::User::find(session, userId);
        }

        std::size_t userCount()
        {
            auto transaction{ session.createReadTransaction() };
            return db::User::getCount(session);
        }

        std::size_t tokenCount(db::UserId userId)
        {
            auto transaction{ session.createReadTransaction() };
            return db::AuthToken::getCount(session, userId);
        }

        db::UserId createUser(std::string_view loginName, std::optional<int> mumaId)
        {
            auto transaction{ session.createWriteTransaction() };
            db::User::pointer user{ session.create<db::User>(loginName) };
            user.modify()->setMumaId(mumaId);
            return user->getId();
        }

        std::unique_ptr<IAuthTokenService> tokens;
    };

    TEST_F(MumaUserSync, createsAnAccountThatDoesNotExistHereYet)
    {
        const MumaSyncSummary summary{ sync(R"([{"id": 1, "username": "user", "is_admin": 1, "enabled": 1}])") };

        EXPECT_EQ(summary.created, 1U);
        const db::User::pointer user{ findByMumaId(1) };
        ASSERT_TRUE(user);
        EXPECT_EQ(user->getLoginName(), "user");
        EXPECT_TRUE(user->isAdmin());
        EXPECT_FALSE(user->isDisabled());
    }

    TEST_F(MumaUserSync, updatesNameAndRoleOfTheLinkedUser)
    {
        const db::UserId userId{ createUser("old-name", 1) };

        const MumaSyncSummary summary{ sync(R"([{"id": 1, "username": "user", "is_admin": false}])") };

        EXPECT_EQ(summary.created, 0U);
        EXPECT_EQ(summary.updated, 1U);
        EXPECT_EQ(userCount(), 1U);
        const db::User::pointer user{ findById(userId) };
        ASSERT_TRUE(user);
        EXPECT_EQ(user->getLoginName(), "user");
        EXPECT_FALSE(user->isAdmin());
        EXPECT_EQ(user->getMumaId(), 1);
    }

    // An LMS user created by a login before the first sync has no MuMa id yet. It is found by name,
    // whatever the case (User::find, bug report 074), and linked -- not duplicated.
    TEST_F(MumaUserSync, linksAnUnlinkedUserFoundByNameInAnyCase)
    {
        const db::UserId userId{ createUser("User", std::nullopt) };

        const MumaSyncSummary summary{ sync(R"([{"id": 3, "username": "user"}])") };

        EXPECT_EQ(summary.created, 0U);
        EXPECT_EQ(userCount(), 1U);
        const db::User::pointer user{ findById(userId) };
        ASSERT_TRUE(user);
        EXPECT_EQ(user->getMumaId(), 3);
        EXPECT_EQ(user->getLoginName(), "user"); // MuMa's spelling is the one spelling
    }

    // A disabled MuMa account kept its Subsonic key: every client holding it went on streaming.
    // Now the user is disabled and every token goes, in every domain -- but the user row, and
    // everything that cascades from it, stays.
    TEST_F(MumaUserSync, aDisabledAccountLosesItsTokensButKeepsItsData)
    {
        const db::UserId userId{ createUser("user", 1) };
        tokens->createAuthToken("subsonic", userId, "subsonic-token-of-user");
        tokens->createAuthToken("ui", userId, "ui-session-of-user");
        db::tests::ScopedTrack track{ session };
        {
            auto transaction{ session.createWriteTransaction() };
            session.create<db::RatedTrack>(track.get(), userId).modify()->setRating(5);
        }

        const MumaSyncSummary summary{ sync(R"([{"id": 1, "username": "user", "enabled": 0}])") };

        EXPECT_EQ(summary.disabled, 1U);
        const db::User::pointer user{ findById(userId) };
        ASSERT_TRUE(user);
        EXPECT_TRUE(user->isDisabled());
        EXPECT_EQ(tokenCount(userId), 0U);
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_TRUE(db::RatedTrack::find(session, track.getId(), userId));
        }

        // A token issued while disabled is revoked again on the next sync, which reports nothing
        // new: the user was disabled already.
        tokens->createAuthToken("subsonic", userId, "issued-while-disabled");
        const MumaSyncSummary again{ sync(R"([{"id": 1, "username": "user", "enabled": false}])") };
        EXPECT_EQ(again.disabled, 0U);
        EXPECT_EQ(tokenCount(userId), 0U);
    }

    TEST_F(MumaUserSync, aReenabledAccountIsEnabledAgain)
    {
        const db::UserId userId{ createUser("user", 1) };
        sync(R"([{"id": 1, "username": "user", "enabled": false}])");

        const MumaSyncSummary summary{ sync(R"([{"id": 1, "username": "user", "enabled": true}])") };

        EXPECT_EQ(summary.reenabled, 1U);
        EXPECT_FALSE(findById(userId)->isDisabled());
    }

    // Deleting an account in MuMa removes it from the list. The LMS user linked to it is renamed to
    // deleted-<id> and disabled; a user with no MuMa id is nobody MuMa knows, and is left alone.
    TEST_F(MumaUserSync, anAccountGoneFromTheListIsRenamedAndDisabled)
    {
        const db::UserId kept{ createUser("user", 1) };
        const db::UserId deleted{ createUser("gone", 2) };
        const db::UserId local{ createUser("local", std::nullopt) };
        tokens->createAuthToken("subsonic", deleted, "subsonic-token-of-gone");

        const MumaSyncSummary summary{ sync(R"([{"id": 1, "username": "user"}])") };

        EXPECT_EQ(summary.disabled, 1U);
        EXPECT_EQ(summary.tombstoned, 1U);
        EXPECT_FALSE(findById(kept)->isDisabled());
        EXPECT_EQ(findById(kept)->getLoginName(), "user");
        EXPECT_TRUE(findById(deleted)->isDisabled());
        EXPECT_EQ(findById(deleted)->getLoginName(), "deleted-2");
        EXPECT_EQ(findById(deleted)->getMumaId(), 2);
        EXPECT_EQ(tokenCount(deleted), 0U);
        EXPECT_FALSE(findById(local)->isDisabled());
        EXPECT_EQ(findById(local)->getLoginName(), "local");

        // The next sync finds nothing new to do.
        const MumaSyncSummary again{ sync(R"([{"id": 1, "username": "user"}])") };
        EXPECT_EQ(again.disabled, 0U);
        EXPECT_EQ(again.tombstoned, 0U);
        EXPECT_EQ(findById(deleted)->getLoginName(), "deleted-2");
    }

    // Issue #239: account 12 "anna" is deleted and a new account 13 "anna" is made before LMS
    // syncs. The new account gets a new, empty LMS user; the old one keeps its ratings under
    // deleted-12.
    TEST_F(MumaUserSync, aNameDeletedAndMadeAgainGetsANewEmptyUser)
    {
        const db::UserId old{ createUser("anna", 12) };
        db::tests::ScopedTrack track{ session };
        {
            auto transaction{ session.createWriteTransaction() };
            session.create<db::RatedTrack>(track.get(), old).modify()->setRating(5);
        }

        const MumaSyncSummary summary{ sync(R"([{"id": 13, "username": "Anna"}])") };

        EXPECT_EQ(summary.failed, 0U);
        EXPECT_EQ(summary.created, 1U);
        EXPECT_EQ(summary.tombstoned, 1U);
        const db::User::pointer fresh{ findByMumaId(13) };
        ASSERT_TRUE(fresh);
        EXPECT_NE(fresh->getId(), old);
        EXPECT_EQ(fresh->getLoginName(), "Anna");
        EXPECT_FALSE(fresh->isDisabled());

        const db::User::pointer tombstone{ findById(old) };
        ASSERT_TRUE(tombstone);
        EXPECT_EQ(tombstone->getLoginName(), "deleted-12");
        EXPECT_EQ(tombstone->getMumaId(), 12);
        EXPECT_TRUE(tombstone->isDisabled());
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_TRUE(db::RatedTrack::find(session, track.getId(), old));
            EXPECT_FALSE(db::RatedTrack::find(session, track.getId(), fresh->getId()));
        }
    }

    // A user deleted before the rename existed is only disabled, under its old name. The next sync
    // renames it too, without counting it as newly disabled.
    TEST_F(MumaUserSync, anEarlierDeletedUserIsRenamedOnTheNextSync)
    {
        const db::UserId old{ createUser("anna", 12) };
        {
            auto transaction{ session.createWriteTransaction() };
            db::User::find(session, old).modify()->setDisabled(true);
        }

        const MumaSyncSummary summary{ sync(R"([{"id": 1, "username": "user"}])") };

        EXPECT_EQ(summary.disabled, 0U);
        EXPECT_EQ(summary.tombstoned, 1U);
        EXPECT_EQ(findById(old)->getLoginName(), "deleted-12");
    }

    // A list that cannot prove account 12 gone renames nobody. The new account 13 with the same
    // name must still not take over account 12's user: its write fails, and a later full list
    // sorts it out.
    TEST_F(MumaUserSync, aUserLinkedToAnotherIdIsNeverTakenOverByName)
    {
        const db::UserId old{ createUser("anna", 12) };

        const MumaSyncSummary summary{ sync(R"([{"id": 13, "username": "anna"}, {"id": "x", "username": "other"}])") };

        EXPECT_EQ(summary.failed, 1U);
        EXPECT_EQ(summary.created, 0U);
        EXPECT_FALSE(findByMumaId(13));
        EXPECT_EQ(findById(old)->getMumaId(), 12);
        EXPECT_EQ(findById(old)->getLoginName(), "anna");

        const MumaSyncSummary full{ sync(R"([{"id": 13, "username": "anna"}])") };
        EXPECT_EQ(full.created, 1U);
        EXPECT_EQ(findById(old)->getLoginName(), "deleted-12");
        ASSERT_TRUE(findByMumaId(13));
        EXPECT_NE(findByMumaId(13)->getId(), old);
    }

    TEST_F(MumaUserSync, tombstoneNameMatchesMusicManager)
    {
        EXPECT_EQ(tombstoneLoginName(12), "deleted-12");
    }

    // An empty list is far likelier a MuMa that answered badly than one with no accounts at all.
    TEST_F(MumaUserSync, anEmptyListDisablesNobody)
    {
        const db::UserId userId{ createUser("user", 1) };

        sync("[]");

        EXPECT_FALSE(findById(userId)->isDisabled());
    }

    // A row whose id cannot be read may be the very account that looks missing.
    TEST_F(MumaUserSync, aListWithAnUnreadableIdDisablesNobodyAsDeleted)
    {
        const db::UserId userId{ createUser("gone", 2) };

        sync(R"([{"id": 1, "username": "user"}, {"id": "two", "username": "gone"}])");

        EXPECT_FALSE(findById(userId)->isDisabled());
    }

    // One malformed row used to end the loop, so every account after it went unsynced. Now each
    // unusable row is skipped and the rest are applied.
    TEST_F(MumaUserSync, aMalformedRowIsSkippedAndTheRestApplied)
    {
        const MumaAccountList list{ parse(R"([
            {"id": 1, "username": "first"},
            {"id": 2},
            "not an account",
            {"id": 3.5, "username": "fraction"},
            {"id": 4, "username": ""},
            {"id": 5, "username": "last"}
        ])") };

        EXPECT_EQ(list.accounts.size(), 2U);
        EXPECT_EQ(list.rejectedRows, 4U);
        EXPECT_FALSE(list.everyRowIdentified);
        // Rows with a readable id count as listed even when rejected for another reason.
        EXPECT_TRUE(list.listedIds.contains(2));
        EXPECT_TRUE(list.listedIds.contains(4));

        const MumaSyncSummary summary{ applyMumaAccounts(session, list) };

        EXPECT_EQ(summary.created, 2U);
        EXPECT_TRUE(findByMumaId(1));
        EXPECT_TRUE(findByMumaId(5));
    }

    // A write that fails -- here two LMS users both claim MuMa id 7, so looking it up throws -- is
    // logged and skipped. It used to take every account after it down, and the thread's session with
    // it; the accounts after it are applied and the session still writes afterwards.
    TEST_F(MumaUserSync, aFailingWriteIsSkippedAndTheRestApplied)
    {
        createUser("twin-a", 7);
        createUser("twin-b", 7);

        const MumaSyncSummary summary{ sync(R"([{"id": 7, "username": "twin"}, {"id": 8, "username": "after"}])") };

        EXPECT_EQ(summary.failed, 1U);
        EXPECT_EQ(summary.created, 1U);
        EXPECT_TRUE(findByMumaId(8));
        EXPECT_NO_THROW(createUser("still-writable", std::nullopt));
    }

    TEST_F(MumaUserSync, parsesBooleansInEitherShapeAndDefaultsToEnabled)
    {
        const MumaAccountList list{ parse(R"([
            {"id": 1, "username": "a", "is_admin": true, "enabled": false},
            {"id": 2, "username": "b", "is_admin": 0, "enabled": 1},
            {"id": 3, "username": "c"}
        ])") };

        ASSERT_EQ(list.accounts.size(), 3U);
        EXPECT_TRUE(list.accounts[0].isAdmin);
        EXPECT_FALSE(list.accounts[0].enabled);
        EXPECT_FALSE(list.accounts[1].isAdmin);
        EXPECT_TRUE(list.accounts[1].enabled);
        EXPECT_FALSE(list.accounts[2].isAdmin);
        EXPECT_TRUE(list.accounts[2].enabled);
        EXPECT_TRUE(list.everyRowIdentified);
    }

    TEST_F(MumaUserSync, aBodyThatIsNotAListYieldsNothing)
    {
        EXPECT_FALSE(parseMumaAccounts(R"({"detail": "Forbidden"})"));
        EXPECT_FALSE(parseMumaAccounts("<html>502 Bad Gateway</html>"));
        EXPECT_FALSE(parseMumaAccounts(""));
    }
} // namespace lms::auth::musicManagement::tests
