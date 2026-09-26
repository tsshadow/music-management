#pragma once

#include "api/muma/Authentication.hpp"
#include "core/ConcurrencyGate.hpp"
#include "core/http/IClient.hpp"
#include "database/IDb.hpp"
#include <Wt/WResource.h>
#include <boost/asio/io_context.hpp>

namespace lms::auth
{
    class IUserSynchronizer;
}

namespace lms::db
{
    class Session;
}

namespace lms::api::muma
{
    class MumaResource : public Wt::WResource
    {
    public:
        MumaResource(boost::asio::io_context& ioContext, db::IDb& db, auth::IUserSynchronizer& userSynchronizer);
        ~MumaResource();

        void handleRequest(const Wt::Http::Request& request, Wt::Http::Response& response) override;

    private:
        /// Asks MuMa (`GET /api/auth/verify`) whose key this is, through a short-lived cache.
        /// Answers `Unavailable` rather than `Invalid` whenever MuMa could not be asked.
        KeyVerdict verifyKeyWithMuma(std::string_view key);

        /// Checks the request's credentials (key, Subsonic u/t/s, or Subsonic u/p) -- see
        /// muma::authenticate. `session` must be inside a transaction: the u/t/s check reads the
        /// user's Subsonic tokens through it.
        AuthDecision authenticateRequest(const Wt::Http::Request& request, bool publicAuthPath, db::Session& session);

        db::IDb& _db;
        auth::IUserSynchronizer& _userSynchronizer;
        std::unique_ptr<core::http::IClient> _httpClient;
        std::string _mumaApiUrl;
        std::string _mumaApiKey;
        // Bounds how many of these handlers may sit waiting on MuMa at once. See
        // core::ConcurrencyGate: each waiting handler is holding an HTTP server thread, and there
        // are only as many of those as the machine has cores.
        core::ConcurrencyGate _mumaCallGate;
        // MuMa's positive verdicts on keys, kept briefly so a page of requests carrying the same key
        // costs one verify round trip rather than one each. Cleared on /users/sync.
        KeyVerdictCache _keyVerdictCache;
    };
} // namespace lms::api::muma
