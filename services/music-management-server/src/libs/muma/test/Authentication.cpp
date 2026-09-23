#include "api/muma/Authentication.hpp"

#include <gtest/gtest.h>

#include <string>
#include <vector>

namespace lms::api::muma::tests
{
    namespace
    {
        constexpr std::string_view lmsApiKey{ "lms-configured-api-key" };
        constexpr long long adminLmsUserId{ 1 };
        constexpr long long bobMumaUserId{ 7 };
        constexpr long long aliceMumaUserId{ 8 };

        /// A MuMa that knows no key at all, and records every key it was asked about.
        struct RecordingVerifier
        {
            KeyVerdict answer{ .state = KeyVerdict::State::Invalid };
            std::vector<std::string> asked;

            /// The function authenticate() calls.
            KeyVerifier asFunction()
            {
                return [this](std::string_view key) {
                    asked.emplace_back(key);
                    return answer;
                };
            }
        };

        /// A password service that must not be consulted.
        PasswordChecker passwordMustNotBeChecked()
        {
            return [](std::string_view, std::string_view) {
                ADD_FAILURE() << "the password service was consulted";
                return PasswordCheck{};
            };
        }

        /// A password service that grants exactly one user/password pair.
        PasswordChecker grantsOnly(std::string user, std::string password, long long lmsUserId)
        {
            return [user = std::move(user), password = std::move(password), lmsUserId](std::string_view u, std::string_view p) {
                if (u == user && p == password)
                    return PasswordCheck{ .state = PasswordCheck::State::Granted, .lmsUserId = lmsUserId };
                return PasswordCheck{ .state = PasswordCheck::State::Denied };
            };
        }

        /// A MuMa verify answer for a regular user.
        KeyVerdict mumaUser(long long id, std::string username, bool isAdmin = false)
        {
            return KeyVerdict{ .state = KeyVerdict::State::User, .mumaUserId = id, .username = std::move(username), .isAdmin = isAdmin };
        }

        /// The rights resolveCallerRights() would derive for a MuMa-key caller.
        CallerRights rightsFor(const AuthDecision& decision)
        {
            return CallerRights{ .method = decision.method, .isAdmin = decision.mumaUserIsAdmin, .mumaUserId = decision.mumaUserId };
        }
    } // namespace

    // The reported exploit: GET /muma/api/admin/subsonic-token?u=<admin>&username=<victim>
    // with `X-API-Key: x`. The key is unknown to both LMS and MuMa, so nothing is granted.
    TEST(MumaAuthentication, rejectsAnUnknownKeyEvenWithAnAdminNamedInU)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .headerKey = "x", .user = "admin" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Unauthorized);
        EXPECT_EQ(decision.method, AuthMethod::None);
        EXPECT_FALSE(mayAdministerServer(rightsFor(decision)));
        ASSERT_EQ(muma.asked.size(), 1U);
        EXPECT_EQ(muma.asked.front(), "x");
    }

    TEST(MumaAuthentication, rejectsAnUnknownApiKeyQueryParameter)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .paramKey = "x" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Unauthorized);
        EXPECT_TRUE(decision.forwardKey.empty());
    }

    TEST(MumaAuthentication, acceptsTheConfiguredLmsApiKeyWithoutAskingMuma)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .headerKey = lmsApiKey }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
        EXPECT_EQ(decision.method, AuthMethod::LmsApiKey);
        EXPECT_TRUE(muma.asked.empty());
    }

    TEST(MumaAuthentication, acceptsTheMumaSystemKey)
    {
        RecordingVerifier muma;
        muma.answer = KeyVerdict{ .state = KeyVerdict::State::System };
        const AuthDecision decision{ authenticate({ .headerKey = "muma-system-key" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
        EXPECT_EQ(decision.method, AuthMethod::MumaSystemKey);
        EXPECT_TRUE(isSystemCaller(rightsFor(decision)));
        EXPECT_TRUE(mayTriggerUserSync(rightsFor(decision)));
    }

    TEST(MumaAuthentication, anEmptyConfiguredLmsApiKeyMatchesNothing)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .headerKey = "", .paramKey = "" }, "", muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Unauthorized);
        EXPECT_TRUE(muma.asked.empty());
    }

    // A system key is a service, not a person, and this server hands its own api-key to every
    // user who logs in through /api/auth/login -- so it opens no admin route here.
    TEST(MumaAuthentication, aSystemKeyIsNotAnAdminUser)
    {
        EXPECT_FALSE(mayAdministerServer(CallerRights{ .method = AuthMethod::LmsApiKey }));
        EXPECT_FALSE(mayAdministerServer(CallerRights{ .method = AuthMethod::MumaSystemKey }));
        EXPECT_FALSE(mayAccessUserSettings(CallerRights{ .method = AuthMethod::MumaSystemKey }, bobMumaUserId));
    }

    TEST(MumaAuthentication, ignoresUWhenAuthenticatedWithTheLmsApiKey)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .headerKey = lmsApiKey, .user = "admin" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        ASSERT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
        EXPECT_FALSE(decision.lmsUserId.has_value());
        EXPECT_FALSE(decision.mumaUserId.has_value());
        EXPECT_TRUE(decision.mumaUsername.empty());
        EXPECT_FALSE(mayAdministerServer(rightsFor(decision)));
    }

    TEST(MumaAuthentication, namesTheCallerFromMumasAnswerNotFromU)
    {
        RecordingVerifier muma;
        muma.answer = mumaUser(bobMumaUserId, "bob");
        const AuthDecision decision{ authenticate({ .headerKey = "bobs-key", .user = "admin" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        ASSERT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
        EXPECT_EQ(decision.method, AuthMethod::MumaUserKey);
        EXPECT_EQ(decision.mumaUsername, "bob");
        EXPECT_EQ(decision.mumaUserId, bobMumaUserId);
        EXPECT_FALSE(decision.lmsUserId.has_value());
        EXPECT_FALSE(mayAdministerServer(rightsFor(decision)));
    }

    TEST(MumaAuthentication, aMumaAdminKeyMayAdministerTheServer)
    {
        RecordingVerifier muma;
        muma.answer = mumaUser(bobMumaUserId, "bob", true);
        const AuthDecision decision{ authenticate({ .headerKey = "bobs-key" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_TRUE(mayAdministerServer(rightsFor(decision)));
    }

    TEST(MumaAuthentication, aUserMayOnlyReachTheirOwnSettings)
    {
        const CallerRights bob{ .method = AuthMethod::MumaUserKey, .mumaUserId = bobMumaUserId };
        EXPECT_TRUE(mayAccessUserSettings(bob, bobMumaUserId));
        EXPECT_FALSE(mayAccessUserSettings(bob, aliceMumaUserId));

        const CallerRights admin{ .method = AuthMethod::Password, .isAdmin = true };
        EXPECT_TRUE(mayAccessUserSettings(admin, aliceMumaUserId));

        const CallerRights withoutMumaId{ .method = AuthMethod::Password };
        EXPECT_FALSE(mayAccessUserSettings(withoutMumaId, aliceMumaUserId));
    }

    TEST(MumaAuthentication, aValidPasswordNamesTheUserThePasswordServiceGranted)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .user = "user", .password = "secret" }, lmsApiKey, muma.asFunction(), grantsOnly("user", "secret", adminLmsUserId)) };

        ASSERT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
        EXPECT_EQ(decision.method, AuthMethod::Password);
        EXPECT_EQ(decision.lmsUserId, adminLmsUserId);
        EXPECT_TRUE(decision.forwardKey.empty());
        EXPECT_TRUE(muma.asked.empty());
    }

    TEST(MumaAuthentication, decodesAnEncodedSubsonicPassword)
    {
        RecordingVerifier muma;
        // "secret" in hex.
        const AuthDecision decision{ authenticate({ .user = "user", .password = "enc:736563726574" }, lmsApiKey, muma.asFunction(), grantsOnly("user", "secret", adminLmsUserId)) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
    }

    TEST(MumaAuthentication, aWrongPasswordIsRejected)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .user = "admin", .password = "guess" }, lmsApiKey, muma.asFunction(), grantsOnly("admin", "secret", adminLmsUserId)) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Unauthorized);
    }

    TEST(MumaAuthentication, aRejectedKeyStillLetsAValidPasswordThrough)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .headerKey = "stale", .user = "user", .password = "secret" }, lmsApiKey, muma.asFunction(), grantsOnly("user", "secret", adminLmsUserId)) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
        EXPECT_EQ(decision.method, AuthMethod::Password);
        // The stale key is not forwarded: it was never verified.
        EXPECT_TRUE(decision.forwardKey.empty());
    }

    TEST(MumaAuthentication, muMaUnreachableIsBackendUnavailableNotUnauthorized)
    {
        RecordingVerifier muma;
        muma.answer = KeyVerdict{ .state = KeyVerdict::State::Unavailable };
        const AuthDecision decision{ authenticate({ .headerKey = "some-key" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::BackendUnavailable);
    }

    TEST(MumaAuthentication, noCredentialsAtAllIsUnauthorized)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({}, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Unauthorized);
        EXPECT_TRUE(muma.asked.empty());
    }

    TEST(MumaAuthentication, aPublicAuthPathNeedsNoCredentials)
    {
        RecordingVerifier muma;
        const AuthDecision decision{ authenticate({ .isPublicPath = true }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        EXPECT_EQ(decision.outcome, AuthDecision::Outcome::Authenticated);
        EXPECT_EQ(decision.method, AuthMethod::PublicPath);
        EXPECT_TRUE(decision.forwardKey.empty());
        EXPECT_FALSE(mayAdministerServer(rightsFor(decision)));
        EXPECT_FALSE(isUserCaller(rightsFor(decision)));
    }

    // The generic proxy forwards AuthDecision::forwardKey and nothing else. It is only ever the
    // key the caller presented -- never the configured MuMa system key, which used to be added
    // whenever the caller sent no X-API-Key header.
    TEST(MumaAuthentication, theProxyKeyIsOnlyEverTheCallersOwn)
    {
        RecordingVerifier muma;
        muma.answer = mumaUser(bobMumaUserId, "bob");

        const AuthDecision viaHeader{ authenticate({ .headerKey = "bobs-key" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };
        EXPECT_EQ(viaHeader.forwardKey, "bobs-key");

        const AuthDecision viaParam{ authenticate({ .paramKey = "bobs-key" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };
        EXPECT_EQ(viaParam.forwardKey, "bobs-key");

        const AuthDecision viaPassword{ authenticate({ .user = "user", .password = "secret" }, lmsApiKey, muma.asFunction(), grantsOnly("user", "secret", adminLmsUserId)) };
        EXPECT_TRUE(viaPassword.forwardKey.empty());

        const AuthDecision publicPath{ authenticate({ .isPublicPath = true }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };
        EXPECT_TRUE(publicPath.forwardKey.empty());
    }

    TEST(MumaAuthentication, theHeaderKeyWinsOverTheQueryParameter)
    {
        RecordingVerifier muma;
        muma.answer = mumaUser(bobMumaUserId, "bob");
        const AuthDecision decision{ authenticate({ .headerKey = "header-key", .paramKey = "param-key" }, lmsApiKey, muma.asFunction(), passwordMustNotBeChecked()) };

        ASSERT_EQ(muma.asked.size(), 1U);
        EXPECT_EQ(muma.asked.front(), "header-key");
        EXPECT_EQ(decision.forwardKey, "header-key");
    }

    TEST(MumaAuthentication, parsesMumasVerifyAnswers)
    {
        EXPECT_EQ(parseVerifyResponse(200, R"({"status":"ok","type":"system"})").state, KeyVerdict::State::System);

        const KeyVerdict user{ parseVerifyResponse(200, R"({"status":"ok","type":"user","user":{"id":7,"username":"bob","is_admin":true,"permissions":[]}})") };
        EXPECT_EQ(user.state, KeyVerdict::State::User);
        EXPECT_EQ(user.mumaUserId, bobMumaUserId);
        EXPECT_EQ(user.username, "bob");
        EXPECT_TRUE(user.isAdmin);

        EXPECT_EQ(parseVerifyResponse(401, "").state, KeyVerdict::State::Invalid);
        EXPECT_EQ(parseVerifyResponse(403, R"({"detail":"Invalid API Key"})").state, KeyVerdict::State::Invalid);
        EXPECT_EQ(parseVerifyResponse(500, "").state, KeyVerdict::State::Unavailable);
        EXPECT_EQ(parseVerifyResponse(200, "not json").state, KeyVerdict::State::Unavailable);
        EXPECT_EQ(parseVerifyResponse(200, R"({"status":"ok","type":"user","user":{"username":"bob"}})").state, KeyVerdict::State::Unavailable);
    }

    TEST(MumaAuthentication, constantTimeEqualsComparesWholeStrings)
    {
        EXPECT_TRUE(constantTimeEquals("abc", "abc"));
        EXPECT_FALSE(constantTimeEquals("abc", "abd"));
        EXPECT_FALSE(constantTimeEquals("abc", "abcd"));
        EXPECT_FALSE(constantTimeEquals("abc", ""));
        EXPECT_TRUE(constantTimeEquals("", ""));
    }

    TEST(MumaAuthentication, subsonicTokenProblemRefusesAShortToken)
    {
        // 15 characters: one short of /updateUser's floor.
        const std::optional<std::string> problem{ subsonicTokenProblem("abcdefghijklmno") };
        ASSERT_TRUE(problem.has_value());
        EXPECT_EQ(*problem, "token must be at least 16 characters");
    }

    TEST(MumaAuthentication, subsonicTokenProblemAcceptsTheFloorAndRevocation)
    {
        EXPECT_EQ(subsonicTokenProblem("abcdefghijklmnop"), std::nullopt);
        EXPECT_EQ(subsonicTokenProblem("a-considerably-longer-subsonic-token"), std::nullopt);
        // Empty means "revoke every token", which the route must keep allowing.
        EXPECT_EQ(subsonicTokenProblem(""), std::nullopt);
    }

    TEST(KeyVerdictCache, remembersAPositiveVerdictUntilItExpires)
    {
        KeyVerdictCache cache{ std::chrono::seconds{ 60 }, 16 };
        const auto now{ KeyVerdictCache::Clock::now() };
        cache.store("bobs-key", mumaUser(bobMumaUserId, "bob"), now);

        const auto hit{ cache.find("bobs-key", now + std::chrono::seconds{ 59 }) };
        ASSERT_TRUE(hit.has_value());
        EXPECT_EQ(hit->username, "bob");

        EXPECT_FALSE(cache.find("bobs-key", now + std::chrono::seconds{ 60 }).has_value());
        EXPECT_FALSE(cache.find("someone-elses-key", now).has_value());
    }

    TEST(KeyVerdictCache, neverStoresARejectionOrAnOutage)
    {
        KeyVerdictCache cache{ std::chrono::seconds{ 60 }, 16 };
        const auto now{ KeyVerdictCache::Clock::now() };
        cache.store("bad", KeyVerdict{ .state = KeyVerdict::State::Invalid }, now);
        cache.store("unknown", KeyVerdict{ .state = KeyVerdict::State::Unavailable }, now);

        EXPECT_EQ(cache.size(), 0U);
    }

    TEST(KeyVerdictCache, staysWithinItsBound)
    {
        KeyVerdictCache cache{ std::chrono::seconds{ 60 }, 2 };
        const auto now{ KeyVerdictCache::Clock::now() };
        cache.store("a", mumaUser(1, "a"), now);
        cache.store("b", mumaUser(2, "b"), now);
        cache.store("c", mumaUser(3, "c"), now);

        EXPECT_LE(cache.size(), 2U);
        EXPECT_TRUE(cache.find("c", now).has_value());
    }

    TEST(KeyVerdictCache, clearForgetsEverything)
    {
        KeyVerdictCache cache{ std::chrono::seconds{ 60 }, 16 };
        const auto now{ KeyVerdictCache::Clock::now() };
        cache.store("bobs-key", mumaUser(bobMumaUserId, "bob"), now);
        cache.clear();

        EXPECT_FALSE(cache.find("bobs-key", now).has_value());
    }
} // namespace lms::api::muma::tests
