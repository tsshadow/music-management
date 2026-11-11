/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include "api/muma/Routing.hpp"

namespace lms::api::muma::tests
{
    // The resource's allow-list: `/users/` is answered here, `/api/` is proxied, and nothing else
    // goes anywhere. A path that merely contains "/api/" further in is not an API path.
    TEST(MumaRouting, onlyUsersAndApiPathsAreRouted)
    {
        EXPECT_EQ(classifyRouteFamily("/users/sync"), RouteFamily::Users);
        EXPECT_EQ(classifyRouteFamily("/users/5/settings/web"), RouteFamily::Users);
        EXPECT_EQ(classifyRouteFamily("/api/radio/channels"), RouteFamily::Api);
        EXPECT_EQ(classifyRouteFamily("/api/"), RouteFamily::Api);

        EXPECT_EQ(classifyRouteFamily(""), RouteFamily::Unknown);
        EXPECT_EQ(classifyRouteFamily("/"), RouteFamily::Unknown);
        EXPECT_EQ(classifyRouteFamily("/api"), RouteFamily::Unknown);
        EXPECT_EQ(classifyRouteFamily("/users"), RouteFamily::Unknown);
        EXPECT_EQ(classifyRouteFamily("/admin/api/secrets"), RouteFamily::Unknown);
        EXPECT_EQ(classifyRouteFamily("/API/radio"), RouteFamily::Unknown);
        EXPECT_EQ(classifyRouteFamily("//api/radio"), RouteFamily::Unknown);
    }

    TEST(MumaRouting, parsesAUserSettingsPath)
    {
        const auto path{ parseUserSettingsPath("/users/12/settings/ultrasonic") };
        ASSERT_TRUE(path);
        EXPECT_EQ(path->mumaUserId, 12);
        EXPECT_EQ(path->appId, "ultrasonic");
    }

    // Older clients sent the id as "user-12"; the prefix up to the first dash is dropped.
    TEST(MumaRouting, acceptsAPrefixedUserId)
    {
        const auto path{ parseUserSettingsPath("/users/user-12/settings/web") };
        ASSERT_TRUE(path);
        EXPECT_EQ(path->mumaUserId, 12);
        EXPECT_EQ(path->appId, "web");
    }

    // Anything but a plain positive number is refused (400), rather than read up to the first
    // non-digit the way std::stoll did: "12abc" used to be user 12.
    TEST(MumaRouting, refusesAUserIdThatIsNotAPlainNumber)
    {
        for (const char* pathInfo : { "/users/12abc/settings/web", "/users/abc/settings/web", "/users//settings/web", "/users/0/settings/web", "/users/user--3/settings/web", "/users/ 12/settings/web", "/users/99999999999999999999999/settings/web" })
        {
            const auto path{ parseUserSettingsPath(pathInfo) };
            ASSERT_TRUE(path) << pathInfo;
            EXPECT_FALSE(path->mumaUserId) << pathInfo;
        }
    }

    TEST(MumaRouting, otherUserPathsAreNotSettingsPaths)
    {
        EXPECT_FALSE(parseUserSettingsPath("/users/sync"));
        EXPECT_FALSE(parseUserSettingsPath("/users/12"));
        EXPECT_FALSE(parseUserSettingsPath("/api/users/12/settings/web"));
    }

    TEST(MumaRouting, theProxyUrlIsTheEncodedPathPlusTheUntouchedQuery)
    {
        EXPECT_EQ(buildProxyRelativeUrl("/api/artists/Silky Noize/image", ""), "/api/artists/Silky%20Noize/image");
        EXPECT_EQ(buildProxyRelativeUrl("/api/search", "q=a%20b&page=2"), "/api/search?q=a%20b&page=2");
    }

    // Only the caller's own key, the client address this server resolved and the content type
    // travel on; an empty one means no header, never a stand-in.
    TEST(MumaRouting, theProxyForwardsOnlyKeyClientAddressAndContentType)
    {
        EXPECT_EQ(buildProxyHeaders({}), ProxyHeaders{});
        EXPECT_EQ(buildProxyHeaders({ .forwardKey = "callers-key" }), (ProxyHeaders{ { "X-API-Key", "callers-key" } }));
        EXPECT_EQ(buildProxyHeaders({ .forwardedFor = "192.0.2.7" }), (ProxyHeaders{ { "X-Forwarded-For", "192.0.2.7" } }));
        EXPECT_EQ(buildProxyHeaders({ .contentType = "application/json" }), (ProxyHeaders{ { "Content-Type", "application/json" } }));
        EXPECT_EQ(buildProxyHeaders({ .forwardKey = "callers-key", .forwardedFor = "192.0.2.7", .contentType = "application/json" }),
                  (ProxyHeaders{ { "X-API-Key", "callers-key" }, { "X-Forwarded-For", "192.0.2.7" }, { "Content-Type", "application/json" } }));
    }

    // The verb travels with the request (bug report 116): a PUT, DELETE or PATCH used to leave as
    // a POST, and an unknown verb parked a thread until the timeout instead of a 405.
    TEST(MumaRouting, theProxyForwardsTheVerbItReceived)
    {
        EXPECT_EQ(proxyMethodFor("GET"), ProxyMethod::Get);
        EXPECT_EQ(proxyMethodFor("POST"), ProxyMethod::Post);
        EXPECT_EQ(proxyMethodFor("PUT"), ProxyMethod::Put);
        EXPECT_EQ(proxyMethodFor("DELETE"), ProxyMethod::Delete);
        EXPECT_EQ(proxyMethodFor("PATCH"), ProxyMethod::Patch);
    }

    TEST(MumaRouting, theProxyRefusesAVerbItDoesNotForward)
    {
        EXPECT_FALSE(proxyMethodFor("HEAD").has_value());
        EXPECT_FALSE(proxyMethodFor("OPTIONS").has_value());
        EXPECT_FALSE(proxyMethodFor("get").has_value());
        EXPECT_FALSE(proxyMethodFor("").has_value());
    }
} // namespace lms::api::muma::tests
