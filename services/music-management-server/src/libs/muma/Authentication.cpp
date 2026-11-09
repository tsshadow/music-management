#include "api/muma/Authentication.hpp"

#include <Wt/Json/Object.h>
#include <Wt/Json/Parser.h>
#include <Wt/Json/Value.h>
#include <Wt/Utils.h>
#include <algorithm>
#include <array>
#include <boost/asio/ip/address.hpp>
#include <boost/system/error_code.hpp>
#include <utility>

#include "core/String.hpp"
#include "endpoints/UserSettingsValidation.hpp"

namespace lms::api::muma
{
    namespace
    {
        constexpr int httpOk{ 200 };
        constexpr int httpUnauthorized{ 401 };
        constexpr int httpForbidden{ 403 };
        constexpr std::string_view encodedPasswordPrefix{ "enc:" };

        /// The key the caller presents: the header when there is one, the `apiKey` parameter otherwise.
        std::string_view presentedKey(const RequestCredentials& credentials)
        {
            return credentials.headerKey.empty() ? credentials.paramKey : credentials.headerKey;
        }

        /// Turns MuMa's `user` object from the verify answer into a verdict, or `Unavailable` when
        /// it lacks the id that the whole mapping onto an LMS user depends on.
        KeyVerdict userVerdictFrom(const Wt::Json::Object& user)
        {
            const Wt::Json::Value& id{ user.get("id") };
            if (id.type() != Wt::Json::Type::Number)
                return KeyVerdict::withState(KeyVerdict::State::Unavailable);

            KeyVerdict verdict{ KeyVerdict::withState(KeyVerdict::State::User) };
            verdict.mumaUserId = static_cast<long long>(id);
            verdict.username = user.get("username").toString().orIfNull("");
            verdict.isAdmin = user.get("is_admin").toBool().orIfNull(false);
            return verdict;
        }

        /// Fills in the parts of an Authenticated decision that come from an accepted key.
        AuthDecision acceptKey(std::string_view key, const KeyVerdict& verdict, AuthMethod method)
        {
            AuthDecision decision{ AuthDecision::withOutcome(AuthDecision::Outcome::Authenticated) };
            decision.method = method;
            decision.forwardKey = std::string{ key };
            if (method == AuthMethod::MumaUserKey)
            {
                decision.mumaUserId = verdict.mumaUserId;
                decision.mumaUsername = verdict.username;
                decision.mumaUserIsAdmin = verdict.isAdmin;
            }
            return decision;
        }

        /// Checks a presented key. Returns a decision when the key settles it (accepted), and
        /// otherwise the outcome a failed key leads to if no password rescues the request.
        AuthDecision checkKey(const RequestCredentials& credentials, std::string_view lmsApiKey, const KeyVerifier& verifyWithMuma)
        {
            const std::string_view key{ presentedKey(credentials) };
            if (!lmsApiKey.empty() && constantTimeEquals(key, lmsApiKey))
                return acceptKey(key, KeyVerdict::withState(KeyVerdict::State::System), AuthMethod::LmsApiKey);

            const KeyVerdict verdict{ verifyWithMuma ? verifyWithMuma(key) : KeyVerdict::withState(KeyVerdict::State::Unavailable) };
            switch (verdict.state)
            {
            case KeyVerdict::State::System:
                return acceptKey(key, verdict, AuthMethod::MumaSystemKey);
            case KeyVerdict::State::User:
                return acceptKey(key, verdict, AuthMethod::MumaUserKey);
            case KeyVerdict::State::Unavailable:
                return AuthDecision::withOutcome(AuthDecision::Outcome::BackendUnavailable);
            case KeyVerdict::State::Invalid:
                break;
            }
            return AuthDecision::withOutcome(AuthDecision::Outcome::Unauthorized);
        }

        /// Checks a u/p pair. The user id comes from the password service's answer, never from `u`.
        AuthDecision checkPasswordPair(const RequestCredentials& credentials, const PasswordChecker& checker)
        {
            if (!checker || !credentials.user || !credentials.password)
                return AuthDecision::withOutcome(AuthDecision::Outcome::Unauthorized);

            const PasswordCheck result{ checker(*credentials.user, decodeSubsonicPassword(*credentials.password)) };
            switch (result.state)
            {
            case PasswordCheck::State::Granted:
                {
                    AuthDecision decision{ AuthDecision::withOutcome(AuthDecision::Outcome::Authenticated) };
                    decision.method = AuthMethod::Password;
                    decision.lmsUserId = result.lmsUserId;
                    return decision;
                }
            case PasswordCheck::State::BackendError:
                return AuthDecision::withOutcome(AuthDecision::Outcome::BackendUnavailable);
            case PasswordCheck::State::Denied:
                break;
            }
            return AuthDecision::withOutcome(AuthDecision::Outcome::Unauthorized);
        }

        /// Checks a u/t/s triple. As for u/p, the user id comes from the checker, never from `u`.
        AuthDecision checkTokenTriple(const RequestCredentials& credentials, const TokenChecker& checker)
        {
            if (!checker || !credentials.user || !credentials.token || !credentials.salt)
                return AuthDecision::withOutcome(AuthDecision::Outcome::Unauthorized);

            const PasswordCheck result{ checker(*credentials.user, *credentials.token, *credentials.salt) };
            switch (result.state)
            {
            case PasswordCheck::State::Granted:
                {
                    AuthDecision decision{ AuthDecision::withOutcome(AuthDecision::Outcome::Authenticated) };
                    decision.method = AuthMethod::SubsonicToken;
                    decision.lmsUserId = result.lmsUserId;
                    return decision;
                }
            case PasswordCheck::State::BackendError:
                return AuthDecision::withOutcome(AuthDecision::Outcome::BackendUnavailable);
            case PasswordCheck::State::Denied:
                break;
            }
            return AuthDecision::withOutcome(AuthDecision::Outcome::Unauthorized);
        }
    } // namespace

    bool constantTimeEquals(std::string_view lhs, std::string_view rhs)
    {
        // Every byte of the longer input is visited whatever the contents, and the length
        // difference is folded into the result rather than returned early on.
        const std::size_t length{ std::max(lhs.size(), rhs.size()) };
        unsigned char difference{ static_cast<unsigned char>(lhs.size() != rhs.size() ? 1 : 0) };
        for (std::size_t i{}; i < length; ++i)
        {
            const auto left{ static_cast<unsigned char>(i < lhs.size() ? lhs.at(i) : 0) };
            const auto right{ static_cast<unsigned char>(i < rhs.size() ? rhs.at(i) : 0) };
            difference |= static_cast<unsigned char>(left ^ right);
        }
        return difference == 0;
    }

    std::string decodeSubsonicPassword(std::string_view password)
    {
        if (password.starts_with(encodedPasswordPrefix))
        {
            if (auto decoded{ core::stringUtils::stringFromHex(password.substr(encodedPasswordPrefix.size())) })
                return std::move(*decoded);
        }
        return std::string{ password };
    }

    KeyVerdict parseVerifyResponse(int status, std::string_view body)
    {
        if (status == httpUnauthorized || status == httpForbidden)
            return KeyVerdict::withState(KeyVerdict::State::Invalid);
        if (status != httpOk)
            return KeyVerdict::withState(KeyVerdict::State::Unavailable);

        Wt::Json::Object root;
        Wt::Json::ParseError error;
        if (!Wt::Json::parse(std::string{ body }, root, error, false))
            return KeyVerdict::withState(KeyVerdict::State::Unavailable);

        if (root.get("status").toString().orIfNull("") != "ok")
            return KeyVerdict::withState(KeyVerdict::State::Unavailable);

        const std::string type{ root.get("type").toString().orIfNull("") };
        if (type == "system")
            return KeyVerdict::withState(KeyVerdict::State::System);
        if (type == "user" && root.get("user").type() == Wt::Json::Type::Object)
            return userVerdictFrom(root.get("user"));

        return KeyVerdict::withState(KeyVerdict::State::Unavailable);
    }

    AuthDecision authenticate(const RequestCredentials& credentials, std::string_view lmsApiKey, const KeyVerifier& verifyWithMuma, const PasswordChecker& checkPassword, const TokenChecker& checkToken)
    {
        // Credential-less entry points (login setup, Google). MuMa validates these itself; the
        // caller's own key, if it sent one, still travels with them, and nothing local is exposed.
        if (credentials.isPublicPath)
        {
            AuthDecision decision{ AuthDecision::withOutcome(AuthDecision::Outcome::Authenticated) };
            decision.method = AuthMethod::PublicPath;
            decision.forwardKey = std::string{ presentedKey(credentials) };
            return decision;
        }

        AuthDecision keyDecision;
        if (!presentedKey(credentials).empty())
        {
            keyDecision = checkKey(credentials, lmsApiKey, verifyWithMuma);
            if (keyDecision.outcome == AuthDecision::Outcome::Authenticated)
                return keyDecision;
        }

        // Both a password and a token is a conflict on /rest (MultipleConflictingAuthentication...);
        // here the token is simply tried first, and a password is only consulted without one.
        if (credentials.user && credentials.token && credentials.salt)
        {
            AuthDecision tokenDecision{ checkTokenTriple(credentials, checkToken) };
            if (tokenDecision.outcome == AuthDecision::Outcome::Unauthorized && keyDecision.outcome == AuthDecision::Outcome::BackendUnavailable)
                return keyDecision;
            return tokenDecision;
        }

        if (credentials.user && credentials.password)
        {
            AuthDecision passwordDecision{ checkPasswordPair(credentials, checkPassword) };
            // "Could not check" beats "wrong": either failure leaves the request refused, but a
            // client told 503 keeps its credentials and retries, one told 401 logs the user out.
            if (passwordDecision.outcome == AuthDecision::Outcome::Unauthorized && keyDecision.outcome == AuthDecision::Outcome::BackendUnavailable)
                return keyDecision;
            return passwordDecision;
        }

        return AuthDecision::withOutcome(keyDecision.outcome);
    }

    bool isPublicAuthPath(std::string_view pathInfo)
    {
        static constexpr std::array<std::string_view, 5> publicAuthPaths{
            "/api/auth/setup-status",
            "/api/auth/setup",
            "/api/auth/google",
            "/api/auth/access-request",
            "/api/auth/login",
        };
        return std::find(publicAuthPaths.begin(), publicAuthPaths.end(), pathInfo) != publicAuthPaths.end();
    }

    std::string forwardedClientAddress(std::string_view clientAddress)
    {
        boost::system::error_code ec;
        const boost::asio::ip::address address{ boost::asio::ip::make_address(std::string{ clientAddress }, ec) };
        if (ec || address.is_unspecified())
            return {};
        return address.to_string();
    }

    bool isSystemCaller(const CallerRights& rights)
    {
        return rights.method == AuthMethod::LmsApiKey || rights.method == AuthMethod::MumaSystemKey;
    }

    bool isUserCaller(const CallerRights& rights)
    {
        return rights.method == AuthMethod::Password || rights.method == AuthMethod::SubsonicToken || rights.method == AuthMethod::MumaUserKey;
    }

    bool mayAdministerServer(const CallerRights& rights)
    {
        return isUserCaller(rights) && rights.isAdmin;
    }

    bool mayTriggerUserSync(const CallerRights& rights)
    {
        return isSystemCaller(rights) || mayAdministerServer(rights);
    }

    bool mayAccessUserSettings(const CallerRights& rights, long long targetMumaUserId)
    {
        if (!isUserCaller(rights))
            return false;
        return rights.isAdmin || rights.mumaUserId == targetMumaUserId;
    }

    std::optional<std::string> trackRefreshKey(const CallerRights& rights, std::string_view callerKey, std::string_view systemKey)
    {
        if (isSystemCaller(rights))
            return std::string{ systemKey };
        if (rights.method == AuthMethod::MumaUserKey && !callerKey.empty())
            return std::string{ callerKey };
        if (mayAdministerServer(rights))
            return std::string{ systemKey };
        return std::nullopt;
    }

    std::optional<std::string> subsonicTokenProblem(std::string_view token)
    {
        if (token.empty() || subsonic::userSettings::isAcceptableSubsonicToken(token))
            return std::nullopt;
        return "token must be at least " + std::to_string(subsonic::userSettings::minSubsonicTokenLength) + " characters";
    }

    KeyVerdictCache::KeyVerdictCache(std::chrono::seconds ttl, std::size_t maxEntries)
        : _ttl{ ttl }
        , _maxEntries{ maxEntries }
    {
    }

    std::optional<KeyVerdict> KeyVerdictCache::find(std::string_view key, Clock::time_point now)
    {
        const std::scoped_lock lock{ _mutex };
        const auto it{ _entries.find(hashKey(key)) };
        if (it == _entries.end())
            return std::nullopt;
        if (it->second.expiresAt <= now)
        {
            _entries.erase(it);
            return std::nullopt;
        }
        return it->second.verdict;
    }

    void KeyVerdictCache::store(std::string_view key, const KeyVerdict& verdict, Clock::time_point now)
    {
        if (verdict.state != KeyVerdict::State::System && verdict.state != KeyVerdict::State::User)
            return;

        const std::scoped_lock lock{ _mutex };
        if (_entries.size() >= _maxEntries)
        {
            std::erase_if(_entries, [now](const auto& entry) { return entry.second.expiresAt <= now; });
            // Still full of live keys: start over rather than grow. The price is one extra round
            // trip per key, which is what an uncached server pays on every request anyway.
            if (_entries.size() >= _maxEntries)
                _entries.clear();
        }
        _entries.insert_or_assign(hashKey(key), Entry{ .verdict = verdict, .expiresAt = now + _ttl });
    }

    void KeyVerdictCache::clear()
    {
        const std::scoped_lock lock{ _mutex };
        _entries.clear();
    }

    std::size_t KeyVerdictCache::size() const
    {
        const std::scoped_lock lock{ _mutex };
        return _entries.size();
    }

    std::string KeyVerdictCache::hashKey(std::string_view key)
    {
        // Wt returns either a string or a byte vector depending on its version; both iterate.
        const auto digest{ Wt::Utils::sha1(std::string{ key }) };
        return std::string(digest.begin(), digest.end());
    }
} // namespace lms::api::muma
