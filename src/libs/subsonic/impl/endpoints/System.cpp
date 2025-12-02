/*
 * Copyright (C) 2025 Emeric Poupon
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

#include "endpoints/System.hpp"

namespace lms::api::subsonic
{
    Response handlePingRequest(RequestContext& context)
    {
        return Response::createOkResponse(context.getServerProtocolVersion());
    }

    Response handleGetLicenseRequest(RequestContext& context)
    {
        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };

        Response::Node& licenseNode{ response.createNode("license") };
        licenseNode.setAttribute("licenseExpires", "2035-09-03T14:46:43");
        licenseNode.setAttribute("email", "foo@bar.com");
        licenseNode.setAttribute("valid", true);

        return response;
    }

    Response handleGetOpenSubsonicExtensions(RequestContext& context)
    {
        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };

        {
            Response::Node& transcodeOffsetNode{ response.createArrayNode("openSubsonicExtensions") };
            transcodeOffsetNode.setAttribute("name", "transcodeOffset");
            transcodeOffsetNode.addArrayValue("versions", 1);
        }

        {
            Response::Node& formPostNode{ response.createArrayNode("openSubsonicExtensions") };
            formPostNode.setAttribute("name", "formPost");
            formPostNode.addArrayValue("versions", 1);
        }

        {
            Response::Node& songLyricsNode{ response.createArrayNode("openSubsonicExtensions") };
            songLyricsNode.setAttribute("name", "songLyrics");
            songLyricsNode.addArrayValue("versions", 1);
        }

        {
            Response::Node& apiKeyAuthentication{ response.createArrayNode("openSubsonicExtensions") };
            apiKeyAuthentication.setAttribute("name", "apiKeyAuthentication");
            apiKeyAuthentication.addArrayValue("versions", 1);
        }

        {
            Response::Node& apiKeyAuthentication{ response.createArrayNode("openSubsonicExtensions") };
            apiKeyAuthentication.setAttribute("name", "getPodcastEpisode");
            apiKeyAuthentication.addArrayValue("versions", 1);
        }

        {
            Response::Node& apiKeyAuthentication{ response.createArrayNode("openSubsonicExtensions") };
            apiKeyAuthentication.setAttribute("name", "indexBasedQueue");
            apiKeyAuthentication.addArrayValue("versions", 1);
        }

        return response;
    };
} // namespace lms::api::subsonic
