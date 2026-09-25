/*
 * Copyright (C) 2025 Junie
 *
 * This file is part of LMS.
 */

#include "UserSynchronizer.hpp"

#include <limits>
#include <vector>

#include <Wt/Dbo/Session.h>
#include <Wt/Http/Client.h>
#include <Wt/Json/Array.h>
#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>
#include <Wt/Json/Value.h>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "core/http/ClientRequestParameters.hpp"
#include "core/http/IClient.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/AuthToken.hpp"
#include "database/objects/User.hpp"

#include "MumaUserSync.hpp"

namespace lms::auth
{
    std::unique_ptr<IUserSynchronizer> createUserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db)
    {
        return std::make_unique<musicManagement::UserSynchronizer>(ioContext, db);
    }

    namespace musicManagement
    {
        namespace
        {
            /// A JSON number that is a whole value fitting a MuMa id, or nullopt.
            std::optional<int> readMumaId(const Wt::Json::Value& value)
            {
                if (value.type() != Wt::Json::Type::Number)
                    return std::nullopt;

                const auto number{ static_cast<double>(value) };
                if (number < 1 || number > static_cast<double>(std::numeric_limits<int>::max()) || number != static_cast<double>(static_cast<int>(number)))
                    return std::nullopt;

                return static_cast<int>(number);
            }

            /// MuMa's booleans arrive as JSON booleans or as MariaDB's 0/1. Anything else -- the
            /// field missing included -- is `fallback`.
            bool readFlag(const Wt::Json::Value& value, bool fallback)
            {
                if (value.type() == Wt::Json::Type::Bool)
                    return static_cast<bool>(value);
                if (value.type() == Wt::Json::Type::Number)
                    return static_cast<double>(value) != 0;
                return fallback;
            }

            /// Runs `write` in a transaction of its own. A failure is logged and reported as false;
            /// the transaction then commits nothing of it, so the next account starts clean.
            template<typename Write>
            bool writeIsolated(db::Session& session, std::string_view what, const Write& write)
            {
                try
                {
                    auto transaction{ session.createWriteTransaction() };
                    try
                    {
                        write();
                        // Flushed here, inside the try: the transaction flushes again when it
                        // commits in its destructor, outside every catch, where a throw ends the
                        // process.
                        session.getDboSession()->flush();
                    }
                    catch (...)
                    {
                        // A failed flush leaves the objects dirty in this thread's session, and
                        // the commit below -- and every later one on this thread -- would try them
                        // again. They go now.
                        session.getDboSession()->discardUnflushed();
                        throw;
                    }
                }
                catch (const std::exception& e)
                {
                    LMS_LOG(AUTH, WARNING, "MusicManagement user sync: skipped " << what << ": " << e.what());
                    return false;
                }
                return true;
            }

            /// Disables the user and revokes every token it holds. Tokens go last, after the flag is
            /// written: a delete runs straight on the database and is not undone by a later throw.
            /// Returns whether the user was enabled before.
            bool disableAndRevoke(db::Session& session, db::User::pointer user)
            {
                const bool wasEnabled{ !user->isDisabled() };
                if (wasEnabled)
                    user.modify()->setDisabled(true);
                session.getDboSession()->flush();
                db::AuthToken::clearAllUserTokens(session, user->getId());
                return wasEnabled;
            }

            void applyAccount(db::Session& session, const MumaAccount& account, MumaSyncSummary& summary)
            {
                const db::UserType type{ account.isAdmin ? db::UserType::ADMIN : db::UserType::REGULAR };

                db::User::pointer user{ db::User::findByMumaId(session, account.mumaId) };
                if (!user)
                    user = db::User::find(session, account.username); // case-insensitive, see User::find

                if (!user)
                {
                    LMS_LOG(AUTH, INFO, "Creating new user '" << account.username << "' from MusicManagement with ID " << account.mumaId);
                    user = session.create<db::User>(account.username);
                    ++summary.created;
                }
                else
                {
                    LMS_LOG(AUTH, DEBUG, "User '" << user->getLoginName() << "' already exists, updating properties.");
                    ++summary.updated;
                }

                user.modify()->setMumaId(account.mumaId);
                user.modify()->setLoginName(account.username);
                user.modify()->setType(type);

                if (!account.enabled)
                {
                    if (disableAndRevoke(session, user))
                    {
                        LMS_LOG(AUTH, INFO, "User '" << account.username << "' is disabled in MusicManagement: disabled here, auth tokens revoked");
                        ++summary.disabled;
                    }
                }
                else if (user->isDisabled())
                {
                    LMS_LOG(AUTH, INFO, "User '" << account.username << "' is enabled again in MusicManagement");
                    user.modify()->setDisabled(false);
                    ++summary.reenabled;
                }
            }

            /// LMS users linked to a MuMa id the list no longer holds.
            std::vector<db::UserId> findUnlistedMumaUsers(db::Session& session, const MumaAccountList& list)
            {
                std::vector<db::UserId> unlisted;
                auto transaction{ session.createReadTransaction() };
                db::User::find(session, db::User::FindParameters{}, [&](const db::User::pointer& user) {
                    const std::optional<int> mumaId{ user->getMumaId() };
                    if (mumaId && !list.listedIds.contains(*mumaId))
                        unlisted.push_back(user->getId());
                });
                return unlisted;
            }

            void disableUnlistedUsers(db::Session& session, const MumaAccountList& list, MumaSyncSummary& summary)
            {
                // An empty list is far more likely a MuMa that answered badly than a MuMa without a
                // single account; and a list with an unreadable id cannot prove any account gone.
                if (list.listedIds.empty() || !list.everyRowIdentified)
                {
                    LMS_LOG(AUTH, WARNING, "MusicManagement user sync: the user list is empty or incomplete, not treating any account as deleted");
                    return;
                }

                for (const db::UserId userId : findUnlistedMumaUsers(session, list))
                {
                    const bool written{ writeIsolated(session, "deleted account (user id " + userId.toString() + ")", [&] {
                        const db::User::pointer user{ db::User::find(session, userId) };
                        if (user && disableAndRevoke(session, user))
                        {
                            LMS_LOG(AUTH, INFO, "User '" << user->getLoginName() << "' no longer exists in MusicManagement: disabled here, auth tokens revoked");
                            ++summary.disabled;
                        }
                    }) };
                    if (!written)
                        ++summary.failed;
                }
            }
        } // namespace

        std::optional<MumaAccountList> parseMumaAccounts(std::string_view body)
        {
            Wt::Json::Value root;
            try
            {
                Wt::Json::parse(std::string{ body }, root);
            }
            catch (const std::exception& e)
            {
                LMS_LOG(AUTH, WARNING, "Failed to parse MusicManagement users: " << e.what());
                return std::nullopt;
            }
            if (root.type() != Wt::Json::Type::Array)
            {
                LMS_LOG(AUTH, WARNING, "Failed to parse MusicManagement users: not a JSON array");
                return std::nullopt;
            }

            MumaAccountList list;
            std::size_t rowIndex{};
            for (const Wt::Json::Value& row : static_cast<const Wt::Json::Array&>(root))
            {
                ++rowIndex;
                if (row.type() != Wt::Json::Type::Object)
                {
                    LMS_LOG(AUTH, WARNING, "MusicManagement user sync: row " << rowIndex << " is not an object, skipped");
                    list.everyRowIdentified = false;
                    ++list.rejectedRows;
                    continue;
                }

                const auto& object{ static_cast<const Wt::Json::Object&>(row) };
                const std::optional<int> mumaId{ readMumaId(object.get("id")) };
                if (!mumaId)
                {
                    LMS_LOG(AUTH, WARNING, "MusicManagement user sync: row " << rowIndex << " has no usable id, skipped");
                    list.everyRowIdentified = false;
                    ++list.rejectedRows;
                    continue;
                }
                list.listedIds.insert(*mumaId);

                const Wt::Json::Value& usernameValue{ object.get("username") };
                std::string username{ usernameValue.type() == Wt::Json::Type::String ? static_cast<std::string>(usernameValue) : std::string{} };
                if (username.empty())
                {
                    LMS_LOG(AUTH, WARNING, "MusicManagement user sync: account " << *mumaId << " has no username, skipped");
                    ++list.rejectedRows;
                    continue;
                }

                list.accounts.push_back(MumaAccount{
                    .mumaId = *mumaId,
                    .username = std::move(username),
                    .isAdmin = readFlag(object.get("is_admin"), false),
                    .enabled = readFlag(object.get("enabled"), true),
                });
            }
            return list;
        }

        MumaSyncSummary applyMumaAccounts(db::Session& session, const MumaAccountList& list)
        {
            MumaSyncSummary summary;

            for (const MumaAccount& account : list.accounts)
            {
                if (!writeIsolated(session, "account '" + account.username + "' (MuMa id " + std::to_string(account.mumaId) + ")", [&] { applyAccount(session, account, summary); }))
                    ++summary.failed;
            }

            disableUnlistedUsers(session, list, summary);

            LMS_LOG(AUTH, INFO, "MusicManagement user sync: " << summary.created << " created, " << summary.updated << " updated, " << summary.disabled << " disabled, " << summary.reenabled << " re-enabled, " << summary.failed << " failed, " << list.rejectedRows << " unusable rows");
            return summary;
        }

        UserSynchronizer::UserSynchronizer(boost::asio::io_context& ioContext, db::IDb& db)
            : _ioContext{ ioContext }
            , _db{ db }
            , _apiUrl{ std::string{ core::Service<core::IConfig>::get()->getString("music-management-url", "") } + "/users/" }
            , _apiKey{ std::string{ core::Service<core::IConfig>::get()->getString("music-management-api-key", "") } }
        {
            LMS_LOG(AUTH, INFO, "Starting MusicManagement user synchronizer... API endpoint = '" << _apiUrl << "'");
            _client = core::http::createClient(_ioContext, _apiUrl);
        }

        UserSynchronizer::~UserSynchronizer()
        {
            LMS_LOG(AUTH, INFO, "Stopped MusicManagement user synchronizer!");
        }

        void UserSynchronizer::setOnUsersSynced(std::function<void()> callback)
        {
            const std::scoped_lock lock{ _onUsersSyncedMutex };
            _onUsersSynced = std::move(callback);
        }

        void UserSynchronizer::notifyUsersSynced()
        {
            std::function<void()> callback;
            {
                const std::scoped_lock lock{ _onUsersSyncedMutex };
                callback = _onUsersSynced;
            }
            if (callback)
                callback();
        }

        void UserSynchronizer::syncUsers()
        {
            // Before the fetch, and regardless of whether it succeeds: the notification itself is
            // the news that a user's standing may have changed. Anything cached about a user is
            // stale from this point even if music-manager cannot be reached for the details.
            notifyUsersSynced();

            if (!_client)
                return;

            LMS_LOG(AUTH, INFO, "Syncing users from MusicManagement...");

            core::http::ClientGETRequestParameters request;
            if (!_apiKey.empty())
            {
                request.headers.emplace_back("X-API-Key", _apiKey);
            }

            request.onSuccessFunc = [this](const Wt::Http::Message& msg) {
                if (msg.status() != 200)
                {
                    LMS_LOG(AUTH, WARNING, "Failed to fetch users from MusicManagement, status: " << msg.status());
                    return;
                }

                if (const std::optional<MumaAccountList> accounts{ parseMumaAccounts(msg.body()) })
                {
                    applyMumaAccounts(_db.getTLSSession(), *accounts);
                    // Again, now that users may have been disabled: a request answered between the
                    // first notification and this point could have cached its grant anew.
                    notifyUsersSynced();
                }
            };

            request.onFailureFunc = []() {
                LMS_LOG(AUTH, WARNING, "Failed to fetch users from MusicManagement, connection error");
            };

            _client->sendGETRequest(std::move(request));
        }
    } // namespace musicManagement
} // namespace lms::auth
