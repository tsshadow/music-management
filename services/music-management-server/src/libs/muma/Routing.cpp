/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "api/muma/Routing.hpp"

#include <algorithm>
#include <stdexcept>

#include "api/muma/PathEncoding.hpp"

namespace lms::api::muma
{
    namespace
    {
        constexpr std::string_view usersPrefix{ "/users/" };
        constexpr std::string_view apiPrefix{ "/api/" };
        constexpr std::string_view settingsSegment{ "/settings/" };

        /// A plain positive decimal number, the whole of `text`, or nullopt.
        std::optional<long long> parsePositiveId(std::string_view text)
        {
            if (text.empty() || !std::ranges::all_of(text, [](char c) { return c >= '0' && c <= '9'; }))
                return std::nullopt;

            try
            {
                const long long value{ std::stoll(std::string{ text }) };
                if (value <= 0)
                    return std::nullopt;
                return value;
            }
            catch (const std::out_of_range&)
            {
                return std::nullopt;
            }
        }
    } // namespace

    RouteFamily classifyRouteFamily(std::string_view pathInfo)
    {
        if (pathInfo.starts_with(usersPrefix))
            return RouteFamily::Users;
        if (pathInfo.starts_with(apiPrefix))
            return RouteFamily::Api;
        return RouteFamily::Unknown;
    }

    std::optional<UserSettingsPath> parseUserSettingsPath(std::string_view pathInfo)
    {
        if (!pathInfo.starts_with(usersPrefix))
            return std::nullopt;

        const std::string_view remaining{ pathInfo.substr(usersPrefix.size()) };
        const std::size_t settingsPos{ remaining.find(settingsSegment) };
        if (settingsPos == std::string_view::npos)
            return std::nullopt;

        std::string_view idText{ remaining.substr(0, settingsPos) };
        if (const std::size_t dashPos{ idText.find('-') }; dashPos != std::string_view::npos)
            idText = idText.substr(dashPos + 1);

        return UserSettingsPath{
            .mumaUserId = parsePositiveId(idText),
            .appId = std::string{ remaining.substr(settingsPos + settingsSegment.size()) },
        };
    }

    std::string buildProxyRelativeUrl(std::string_view decodedPath, std::string_view queryString)
    {
        if (queryString.empty())
            return encodeProxyPath(decodedPath);
        return encodeProxyPath(decodedPath) + "?" + std::string{ queryString };
    }

    ProxyHeaders buildProxyHeaders(const ProxyHeaderInputs& inputs)
    {
        ProxyHeaders headers;
        if (!inputs.forwardKey.empty())
            headers.emplace_back("X-API-Key", std::string{ inputs.forwardKey });
        if (!inputs.forwardedFor.empty())
            headers.emplace_back("X-Forwarded-For", std::string{ inputs.forwardedFor });
        if (!inputs.contentType.empty())
            headers.emplace_back("Content-Type", std::string{ inputs.contentType });
        return headers;
    }

    std::optional<ProxyMethod> proxyMethodFor(std::string_view method)
    {
        if (method == "GET")
            return ProxyMethod::Get;
        if (method == "POST")
            return ProxyMethod::Post;
        if (method == "PUT")
            return ProxyMethod::Put;
        if (method == "DELETE")
            return ProxyMethod::Delete;
        if (method == "PATCH")
            return ProxyMethod::Patch;
        return std::nullopt;
    }
} // namespace lms::api::muma
