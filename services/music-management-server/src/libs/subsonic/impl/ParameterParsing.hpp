/*
 * Copyright (C) 2020 Emeric Poupon
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

#pragma once

#include <Wt/Http/Request.h>

#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "core/String.hpp"
#include "database/Types.hpp"

#include "SubsonicResponse.hpp"

namespace lms::api::subsonic
{

    // Renders the parameters of a request for a log line. A credential (`p`, `password`,
    // `apiKey`, the token `t` and its salt `s`) is replaced by *REDACTED*, and so is a credential
    // inside a value that is itself a URL with a query string, such as a signed getCoverArt URL
    // a client sent as the `id` (MuMa bug report 150).
    std::string parameterMapToDebugString(const Wt::Http::ParameterMap& parameterMap);

    // The same redaction for one value: every `t=`, `s=`, `p=`, `u=`, `password=` or `apiKey=`
    // in a query string inside it, plain or percent-encoded, keeps its name and loses its value.
    std::string redactCredentialsInValue(std::string_view value);

    template<typename T>
    std::vector<T> getMultiParametersAs(const Wt::Http::ParameterMap& parameterMap, const std::string& paramName)
    {
        std::vector<T> res;

        auto it = parameterMap.find(paramName);
        if (it == parameterMap.end())
        {
            for (auto const& [key, val] : parameterMap)
            {
                if (core::stringUtils::stringCaseInsensitiveEqual(key, paramName))
                {
                    it = parameterMap.find(key);
                    break;
                }
            }
        }

        if (it == parameterMap.end())
            return res;

        for (const std::string& param : it->second)
        {
            auto value{ core::stringUtils::readAs<T>(param) };
            if (value)
                res.emplace_back(std::move(*value));
        }

        return res;
    }

    template<typename T>
    std::vector<T> getMandatoryMultiParametersAs(const Wt::Http::ParameterMap& parameterMap, const std::string& param)
    {
        std::vector<T> res{ getMultiParametersAs<T>(parameterMap, param) };
        if (res.empty())
            throw RequiredParameterMissingError{ param };

        return res;
    }

    template<typename T>
    std::optional<T> getParameterAs(const Wt::Http::ParameterMap& parameterMap, const std::string& param)
    {
        std::vector<T> params{ getMultiParametersAs<T>(parameterMap, param) };

        if (params.size() != 1)
            return std::nullopt;

        return T{ std::move(params.front()) };
    }

    template<typename T>
    T getMandatoryParameterAs(const Wt::Http::ParameterMap& parameterMap, const std::string& param)
    {
        auto res{ getParameterAs<T>(parameterMap, param) };
        if (!res)
            throw RequiredParameterMissingError{ param };

        return *res;
    }

    bool hasParameter(const Wt::Http::ParameterMap& parameterMap, const std::string& param);
    std::string decodePasswordIfNeeded(const std::string& password);
} // namespace lms::api::subsonic
