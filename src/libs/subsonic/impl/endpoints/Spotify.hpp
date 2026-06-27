/*
 * copyright (c) 2026 emeric poupon
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

#include <Wt/Http/Response.h>

namespace lms::api::subsonic
{
    class RequestContext;

    Response handleGetSpotifyCuratedPlaylists(RequestContext& ctx);
    std::optional<Response> handleGetSpotifyPlaylist(RequestContext& ctx, const std::string& id);
    Response handleGetSpotifyPlaylistRequest(RequestContext& ctx);
    Response handleGetSpotifyTracks(RequestContext& ctx);
    Response handleGetSpotifyHistory(RequestContext& ctx);
    Response handleSpotifyImportFromListenBrainz(RequestContext& ctx);
} // namespace lms::api::subsonic
