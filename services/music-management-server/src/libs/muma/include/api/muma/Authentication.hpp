#pragma once

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>

namespace lms::api::muma
{
    /// MuMa's answer to "whose key is this?", as given by `GET /api/auth/verify`.
    ///
    /// `Unavailable` means MuMa could not be asked or gave no usable answer. It says nothing about
    /// the key, so it must never be reported to the caller as "wrong key": a client that hears 401
    /// throws its key away.
    struct KeyVerdict
    {
        enum class State : std::uint8_t
        {
            Invalid,
            System,
            User,
            Unavailable,
        };

        State state{ State::Invalid };
        long long mumaUserId{};
        std::string username;
        bool isAdmin{};

        /// A verdict carrying only a state (no user).
        static KeyVerdict withState(State state)
        {
            KeyVerdict verdict;
            verdict.state = state;
            return verdict;
        }
    };

    /// Asks MuMa about a key. A function rather than a direct call so the decision below can be
    /// exercised without a MuMa to talk to.
    using KeyVerifier = std::function<KeyVerdict(std::string_view key)>;

    /// The result of checking a Subsonic username/password pair.
    struct PasswordCheck
    {
        enum class State : std::uint8_t
        {
            Granted,
            Denied,
            BackendError,
        };

        State state{ State::Denied };
        long long lmsUserId{};

        /// A result with the given state and, for Granted, the LMS user it names.
        static PasswordCheck withState(State state, long long lmsUserId = 0)
        {
            PasswordCheck check;
            check.state = state;
            check.lmsUserId = lmsUserId;
            return check;
        }
    };

    /// Checks a Subsonic username/password pair. The password arrives already decoded.
    using PasswordChecker = std::function<PasswordCheck(std::string_view user, std::string_view password)>;

    /// Checks a Subsonic `u`/`t`/`s` triple: whether `token` is `md5(t + salt)` for one of the user's
    /// Subsonic API tokens, exactly as `SubsonicResource::authenticateUser` checks it on `/rest`.
    using TokenChecker = std::function<PasswordCheck(std::string_view user, std::string_view token, std::string_view salt)>;

    /// How the caller proved who they are.
    enum class AuthMethod : std::uint8_t
    {
        None,
        PublicPath,    // one of the credential-less auth entry points; proxied, nothing local
        LmsApiKey,     // this server's own configured `api-key`
        MumaSystemKey, // a key MuMa verified as its system key
        MumaUserKey,   // a key MuMa verified as belonging to one of its users
        Password,      // Subsonic u/p, checked by the password service
        SubsonicToken, // Subsonic u/t/s, checked against the user's Subsonic API tokens
    };

    /// Everything a request offers as credentials. Absent parameters are empty.
    struct RequestCredentials
    {
        std::string_view headerKey;
        std::string_view paramKey;
        std::optional<std::string_view> user;
        std::optional<std::string_view> password;
        std::optional<std::string_view> token; // Subsonic `t`: md5(Subsonic API token + salt)
        std::optional<std::string_view> salt;  // Subsonic `s`
        bool isPublicPath{};
    };

    /// Who the caller is, as far as it has been proven.
    ///
    /// The identity only ever comes from the credential that was verified: MuMa's verify answer for
    /// a user key, the password service's user id for u/p. The bare `u` parameter never names the
    /// caller -- that is how any key used to become any user, admins included.
    struct AuthDecision
    {
        enum class Outcome : std::uint8_t
        {
            Authenticated,
            Unauthorized,
            BackendUnavailable,
        };

        Outcome outcome{ Outcome::Unauthorized };
        AuthMethod method{ AuthMethod::None };

        /// The X-API-Key the generic proxy may put on the request to MuMa: the key the caller
        /// presented, and nothing else. Empty when the caller presented none (u/p callers). The
        /// configured system key is never placed here.
        std::string forwardKey;

        /// Set for `Password` and `SubsonicToken`: the LMS user the credential belongs to.
        std::optional<long long> lmsUserId;
        /// Set for `MumaUserKey`: MuMa's user id, username and admin role from the verify answer.
        std::optional<long long> mumaUserId;
        std::string mumaUsername;
        bool mumaUserIsAdmin{};

        /// A decision with the given outcome and nothing else.
        static AuthDecision withOutcome(Outcome outcome)
        {
            AuthDecision decision;
            decision.outcome = outcome;
            return decision;
        }
    };

    /// Compares two secrets in time that depends on their lengths only, not on how much of them
    /// matches, so a wrong key cannot be guessed one byte at a time.
    bool constantTimeEquals(std::string_view lhs, std::string_view rhs);

    /// Undoes the `enc:<hex>` obfuscation Subsonic clients may apply to a password.
    std::string decodeSubsonicPassword(std::string_view password);

    /// Reads MuMa's `GET /api/auth/verify` answer. 401/403 mean the key is not valid; any other
    /// failure (5xx, a 200 that does not parse) means MuMa could not say.
    KeyVerdict parseVerifyResponse(int status, std::string_view body);

    /// Decides whether a request is authenticated, and as whom.
    ///
    /// A key (header first, then the `apiKey` parameter) counts only if it is this server's own
    /// `api-key` or MuMa confirms it. When it does not, a u/t/s triple (checked by `checkToken`,
    /// no round trip to MuMa) or a u/p pair is still tried, since each is verified on its own;
    /// when none holds, the answer is Unauthorized -- or BackendUnavailable if what failed was the
    /// asking rather than the credential. The token form exists so a web page can sign an `<img>`
    /// URL without putting the login password in it (bug report 103).
    AuthDecision authenticate(const RequestCredentials& credentials, std::string_view lmsApiKey, const KeyVerifier& verifyWithMuma, const PasswordChecker& checkPassword, const TokenChecker& checkToken = {});

    /// Whether `pathInfo` is one of MuMa's credential-less auth entry points (setup, Google, the
    /// access request, and the username/password login). These reach MuMa through the generic
    /// proxy without any check here: the caller has no credentials yet, and MuMa validates them
    /// itself. The login is on this list rather than answered locally, so a web login receives the
    /// user's own MuMa key -- this server used to answer it with its own `api-key`, the same value
    /// for everyone.
    bool isPublicAuthPath(std::string_view pathInfo);

    /// The X-Forwarded-For value this server sends MuMa for a proxied call: the client address it
    /// resolved itself (`Wt::Http::Request::clientAddress()`), normalised, and nothing the client
    /// wrote. Anything the client put in its own X-Forwarded-For is dropped rather than appended,
    /// so the chain MuMa sees starts at this server. Empty when the address does not parse or is
    /// unspecified -- then no header is sent and MuMa keys on this server's own address, as before.
    ///
    /// MuMa's login rate limit counts per client address (services/music_manager/rate_limit.py)
    /// and believes this header only because it comes from a trusted network; without it, every
    /// login reaching MuMa through lms.<domain> came from this server's address.
    std::string forwardedClientAddress(std::string_view clientAddress);

    /// What an authenticated caller may do on the routes this server answers itself.
    struct CallerRights
    {
        AuthMethod method{ AuthMethod::None };
        bool isAdmin{};                      // the verified user is an admin
        std::optional<long long> mumaUserId; // the verified user's MuMa id, when known
    };

    /// A system key: a service, not a person. It authenticates, but it is nobody.
    bool isSystemCaller(const CallerRights& rights);

    /// Whether the caller is a verified person, as opposed to a service or nobody.
    bool isUserCaller(const CallerRights& rights);

    /// Media libraries and Subsonic tokens: a verified admin *user* only. A system key is not
    /// enough: it belongs to a service, not a person, so holding it proves nothing about being an
    /// admin. (Until 0.72.x this server also handed its own `api-key` to every web login.)
    bool mayAdministerServer(const CallerRights& rights);

    /// `/users/sync`: MuMa's own notification (its system key), or an admin.
    bool mayTriggerUserSync(const CallerRights& rights);

    /// `/users/{id}/settings/{app}`, where `id` is a MuMa user id: that user, or an admin.
    bool mayAccessUserSettings(const CallerRights& rights, long long targetMumaUserId);

    /// The X-API-Key a track refresh (`/api/tracks/{id}/refresh`) sends to MuMa's
    /// `rerun-parse-path`, which needs `rules.manage`; nullopt when this caller may not start one.
    /// A MuMa user key goes through as itself, so MuMa judges that user's permissions. A system
    /// caller gets `systemKey`. A u/p or token caller gets `systemKey` only when that LMS user is
    /// an admin: LMS knows the admin role and no other MuMa permission. Issue #230.
    std::optional<std::string> trackRefreshKey(const CallerRights& rights, std::string_view callerKey, std::string_view systemKey);

    /// Why `token` may not be stored as a Subsonic token through `/api/admin/subsonic-token`, or
    /// nullopt when it may. An empty token is acceptable: the route reads it as "revoke". The
    /// length floor is `/updateUser`'s (`userSettings::minSubsonicTokenLength`), so the two ways of
    /// issuing a token cannot disagree about what a token is.
    std::optional<std::string> subsonicTokenProblem(std::string_view token);

    /// Remembers MuMa's positive verdicts for a short while, so a burst of requests carrying the
    /// same key costs one round trip to MuMa rather than one each.
    ///
    /// Keys are stored as a SHA-1 of the key, never the key itself. Only `System` and `User`
    /// verdicts are kept: caching rejections would let anyone fill the cache with random keys,
    /// and an `Unavailable` must be asked again next time.
    class KeyVerdictCache
    {
    public:
        using Clock = std::chrono::steady_clock;

        /// @param ttl how long a verdict is trusted; also how long a revoked key keeps working here
        /// @param maxEntries bound on the number of cached keys
        KeyVerdictCache(std::chrono::seconds ttl, std::size_t maxEntries);

        /// The verdict stored for `key`, if one is stored and has not expired at `now`.
        std::optional<KeyVerdict> find(std::string_view key, Clock::time_point now);

        /// Stores a positive verdict for `key`; anything else is ignored.
        void store(std::string_view key, const KeyVerdict& verdict, Clock::time_point now);

        /// Forgets everything, e.g. when MuMa announces that users changed.
        void clear();

        /// Number of cached keys, expired ones included.
        std::size_t size() const;

    private:
        struct Entry
        {
            KeyVerdict verdict;
            Clock::time_point expiresAt;
        };

        static std::string hashKey(std::string_view key);

        std::chrono::seconds _ttl;
        std::size_t _maxEntries;
        mutable std::mutex _mutex;
        std::unordered_map<std::string, Entry> _entries;
    };
} // namespace lms::api::muma
