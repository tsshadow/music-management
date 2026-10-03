/*
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

#include <algorithm>
#include <array>
#include <string>
#include <string_view>
#include <vector>

#include <Wt/Http/Request.h>

#include "../ParameterParsing.hpp"
#include "../SubsonicResponse.hpp"
#include "core/String.hpp"

namespace lms::api::subsonic
{
    // The forms muma classifies every track under (services/common/track_form.py FORMS), written
    // into track.form by its lms.db sync. A closed set, so an unknown value is refused rather than
    // silently matching nothing -- "no live sets" and "typo" must not look the same.
    // `interview` and `preview` are non-music (docs/designs/non-music-forms/): the music lists
    // leave them out, and naming one here is how a curator lists them.
    inline constexpr std::array<std::string_view, 6> trackForms{ "track", "set", "liveset", "podcast", "interview", "preview" };

    /**
     * The `form` parameter of getSpotifyTracks and getSongs: repeatable, and each value may itself
     * be a comma-separated list (the web filter bar sends scalars). Empty when not given.
     *
     * @throws BadParameterGenericError for a value outside trackForms.
     */
    inline std::vector<std::string> parseTrackForms(const Wt::Http::ParameterMap& parameters)
    {
        std::vector<std::string> forms;
        for (const std::string& value : getMultiParametersAs<std::string>(parameters, "form"))
        {
            for (std::string_view part : core::stringUtils::splitString(value, ','))
            {
                const std::string form{ core::stringUtils::stringTrim(part) };
                if (form.empty())
                    continue;
                if (std::find(trackForms.begin(), trackForms.end(), form) == trackForms.end())
                    throw BadParameterGenericError{ "form", "expected track, set, liveset, podcast, interview or preview" };
                if (std::find(forms.begin(), forms.end(), form) == forms.end())
                    forms.push_back(form);
            }
        }
        return forms;
    }
} // namespace lms::api::subsonic
