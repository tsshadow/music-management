/*
 * Copyright (C) 2023 Emeric Poupon
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

#include "ParameterParsing.hpp"

#include <algorithm>
#include <array>
#include <cctype>

namespace lms::api::subsonic
{
    namespace
    {
        constexpr std::string_view redactedStr{ "*REDACTED*" };

        bool equalsIgnoringCase(std::string_view a, std::string_view b)
        {
            return a.size() == b.size() && std::equal(a.begin(), a.end(), b.begin(), [](char x, char y) {
                       return std::tolower(static_cast<unsigned char>(x)) == std::tolower(static_cast<unsigned char>(y));
                   });
        }

        bool isCredentialParameter(std::string_view name)
        {
            constexpr std::array<std::string_view, 6> credentialNames{ "p", "password", "apiKey", "t", "s", "u" };
            return std::any_of(credentialNames.begin(), credentialNames.end(), [name](std::string_view credential) { return equalsIgnoringCase(name, credential); });
        }

        bool isTopLevelSecret(std::string_view name)
        {
            // The user name stays readable at the top level: it says who sent the request.
            return !equalsIgnoringCase(name, "u") && isCredentialParameter(name);
        }

        // The length of the query separator at `pos`: `?` or `&`, or their percent-encoded forms.
        std::size_t separatorLengthAt(std::string_view text, std::size_t pos)
        {
            if (text[pos] == '?' || text[pos] == '&')
                return 1;
            if (text[pos] == '%' && pos + 2 < text.size())
            {
                const std::string_view code{ text.substr(pos + 1, 2) };
                if (equalsIgnoringCase(code, "3F") || equalsIgnoringCase(code, "26"))
                    return 3;
            }
            return 0;
        }

        // The length of the `=` at `pos`, plain or percent-encoded, or 0 when there is none.
        std::size_t equalsLengthAt(std::string_view text, std::size_t pos)
        {
            if (pos < text.size() && text[pos] == '=')
                return 1;
            if (pos + 2 < text.size() && text[pos] == '%' && equalsIgnoringCase(text.substr(pos + 1, 2), "3D"))
                return 3;
            return 0;
        }

        std::string_view redactTopLevel(const std::string& type, const std::string& value, std::string& scratch)
        {
            if (isTopLevelSecret(type))
                return redactedStr;

            scratch = redactCredentialsInValue(value);
            return scratch;
        }
    } // namespace

    std::string redactCredentialsInValue(std::string_view value)
    {
        std::string res;
        res.reserve(value.size());

        std::size_t pos{};
        while (pos < value.size())
        {
            const std::size_t separatorLength{ separatorLengthAt(value, pos) };
            if (separatorLength == 0)
            {
                res += value[pos++];
                continue;
            }

            res += value.substr(pos, separatorLength);
            pos += separatorLength;

            std::size_t nameEnd{ pos };
            while (nameEnd < value.size() && std::isalpha(static_cast<unsigned char>(value[nameEnd])))
                ++nameEnd;

            const std::size_t equalsLength{ equalsLengthAt(value, nameEnd) };
            const std::string_view name{ value.substr(pos, nameEnd - pos) };
            if (equalsLength == 0 || !isCredentialParameter(name))
                continue;

            res += value.substr(pos, nameEnd + equalsLength - pos);
            res += redactedStr;

            // Skip the secret up to the next parameter.
            pos = nameEnd + equalsLength;
            while (pos < value.size() && value[pos] != '#' && separatorLengthAt(value, pos) == 0)
                ++pos;
        }

        return res;
    }

    std::string parameterMapToDebugString(const Wt::Http::ParameterMap& parameterMap)
    {
        std::string res;
        std::string scratch;

        bool firstParameter{ true };
        for (const auto& [type, values] : parameterMap)
        {
            if (!firstParameter)
                res += ", ";
            firstParameter = false;

            res += "{" + type + "=";
            if (values.size() == 1)
            {
                res += redactTopLevel(type, values.front(), scratch);
            }
            else
            {
                res += "{";
                bool firstValue{ true };
                for (const std::string& value : values)
                {
                    if (!firstValue)
                        res += ',';
                    firstValue = false;

                    res += redactTopLevel(type, value, scratch);
                }
                res += "}";
            }
            res += "}";
        }

        return res;
    }

    bool hasParameter(const Wt::Http::ParameterMap& parameterMap, const std::string& param)
    {
        return parameterMap.find(param) != std::cend(parameterMap);
    }

    std::string decodePasswordIfNeeded(const std::string& password)
    {
        if (password.find("enc:") == 0)
        {
            auto decodedPassword{ core::stringUtils::stringFromHex(password.substr(4)) };
            if (!decodedPassword)
                return password; // fallback on plain password

            return *decodedPassword;
        }

        return password;
    }
} // namespace lms::api::subsonic
