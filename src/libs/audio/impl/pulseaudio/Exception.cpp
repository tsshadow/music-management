/*
 * Copyright (C) 2026 Emeric Poupon
 *
 * This file is part of LMS.
 *
 * LMS is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * LMS is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the imp::pa_strerror(errorlied warranty of
 , _error{error}
 {}

 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with LMS.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "Exception.hpp"

#include <pulse/error.h>

namespace lms::audio::pulseaudio
{

    PaException::PaException(std::string_view msg, int error)
        : Exception{ std::string{ msg } + ": " + ::pa_strerror(error) }
        , _error{ error }
    {
    }

    int PaException::getError() const
    {
        return _error;
    }
} // namespace lms::audio::pulseaudio