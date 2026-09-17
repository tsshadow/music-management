/*
 * Copyright (C) 2021 Emeric Poupon
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

#include <memory>
#include <variant>

#include "core/http/ClientRequestParameters.hpp"

namespace lms::core::http
{
    class ClientRequest
    {
    public:
        ClientRequest(ClientGETRequestParameters&& GETParams)
            : _parameters{ std::move(GETParams) } {}
        ClientRequest(ClientPOSTRequestParameters&& POSTParams)
            : _parameters{ std::move(POSTParams) } {}
        ClientRequest(ClientPUTRequestParameters&& PUTParams)
            : _parameters{ std::move(PUTParams) } {}
        ClientRequest(ClientDELETERequestParameters&& DELETEParams)
            : _parameters{ std::move(DELETEParams) } {}

        std::size_t retryCount{};

        const ClientRequestParameters& getParameters() const
        {
            const ClientRequestParameters* res;

            std::visit([&](const auto& parameters) {
                res = &static_cast<const ClientRequestParameters&>(parameters);
            },
                       _parameters);

            return *res;
        }

        enum class Type
        {
            GET,
            POST,
            PUT,
            DELETE,
        };
        Type getType() const
        {
            if (std::holds_alternative<ClientGETRequestParameters>(_parameters))
                return Type::GET;
            if (std::holds_alternative<ClientPUTRequestParameters>(_parameters))
                return Type::PUT;
            if (std::holds_alternative<ClientDELETERequestParameters>(_parameters))
                return Type::DELETE;
            return Type::POST;
        }

        const ClientGETRequestParameters& getGETParameters() const
        {
            return std::get<ClientGETRequestParameters>(_parameters);
        }

        const ClientPOSTRequestParameters& getPOSTParameters() const
        {
            return std::get<ClientPOSTRequestParameters>(_parameters);
        }

        const ClientPUTRequestParameters& getPUTParameters() const
        {
            return std::get<ClientPUTRequestParameters>(_parameters);
        }

        const ClientDELETERequestParameters& getDELETEParameters() const
        {
            return std::get<ClientDELETERequestParameters>(_parameters);
        }

    private:
        std::variant<ClientGETRequestParameters, ClientPOSTRequestParameters, ClientPUTRequestParameters, ClientDELETERequestParameters> _parameters;
    };
} // namespace lms::core::http
