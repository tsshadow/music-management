/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace lms::api::muma
{
    /// Which part of `/muma` a path belongs to, once the routes answered locally have had their go.
    ///
    /// This is the allow-list of the resource: `/users/...` is answered here (sync, per-user
    /// settings), `/api/...` goes to MuMa through the generic proxy, and anything else is 404 --
    /// it is never forwarded, so a path outside `/api/` cannot reach an arbitrary MuMa route.
    enum class RouteFamily : std::uint8_t
    {
        Users,
        Api,
        Unknown,
    };

    /// Classifies a decoded `pathInfo` (relative to `/muma`).
    RouteFamily classifyRouteFamily(std::string_view pathInfo);

    /// `/users/{id}/settings/{app}`, taken apart.
    struct UserSettingsPath
    {
        /// MuMa's user id; nullopt when the id segment is not a plain positive number, which the
        /// route answers with 400. A `prefix-` before the number (`user-5`) is accepted and
        /// dropped: older clients sent the id that way.
        std::optional<long long> mumaUserId;
        std::string appId;
    };

    /// Parses a settings path, or nullopt when `pathInfo` is not one.
    std::optional<UserSettingsPath> parseUserSettingsPath(std::string_view pathInfo);

    /// The URL, relative to MuMa's base, a proxied request is sent to: the decoded path encoded
    /// again (see encodeProxyPath), then the query string exactly as it arrived.
    std::string buildProxyRelativeUrl(std::string_view decodedPath, std::string_view queryString);

    using ProxyHeaders = std::vector<std::pair<std::string, std::string>>;

    /// What a proxied request may carry to MuMa. Empty fields are left out.
    struct ProxyHeaderInputs
    {
        std::string_view forwardKey;   // the caller's own key (AuthDecision::forwardKey)
        std::string_view forwardedFor; // the client address this server resolved (forwardedClientAddress)
        std::string_view contentType;  // the caller's Content-Type, for requests with a body
    };

    /// The headers a proxied request carries to MuMa, and nothing else: the caller's own key as
    /// `X-API-Key`, the client address as `X-Forwarded-For` (never what the client wrote there),
    /// and its `Content-Type`. Everything else the caller sent -- cookies, its own forwarding
    /// headers, its `Authorization` -- stays here. The configured system key is never among them;
    /// see AuthDecision::forwardKey.
    ProxyHeaders buildProxyHeaders(const ProxyHeaderInputs& inputs);

    /// The HTTP verbs the generic `/api/` proxy forwards to MuMa.
    enum class ProxyMethod : std::uint8_t
    {
        Get,
        Post,
        Put,
        Delete,
        Patch,
    };

    /// The verb a request leaves for MuMa with: the one it arrived with, or nullopt for a verb the
    /// proxy does not forward (answered 405 at once). Every PUT and DELETE used to leave as a POST.
    std::optional<ProxyMethod> proxyMethodFor(std::string_view method);
} // namespace lms::api::muma
