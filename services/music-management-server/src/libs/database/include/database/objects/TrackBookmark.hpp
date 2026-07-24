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

#include <chrono>
#include <optional>

#include <Wt/Dbo/Field.h>

#include "database/IdType.hpp"
#include "database/Object.hpp"
#include "database/Types.hpp"
#include "database/objects/TrackId.hpp"
#include "database/objects/UserId.hpp"

LMS_DECLARE_IDTYPE(TrackBookmarkId)

namespace lms::db
{
    class Session;
    class Track;
    class User;

    class TrackBookmark final : public Object<TrackBookmark, TrackBookmarkId>
    {
    public:
        TrackBookmark() = default;

        // Find utility functions
        static std::size_t getCount(Session& session);
        static pointer find(Session& session, TrackBookmarkId id);
        static RangeResults<TrackBookmarkId> find(Session& session, UserId userId, std::optional<Range> range = std::nullopt);
        static pointer find(Session& session, UserId userId, TrackId trackId);

        // Setters
        void setOffset(std::chrono::milliseconds offset) { _offset = offset; }
        void setComment(std::string_view comment) { _comment = comment; }

        // Getters
        std::chrono::milliseconds getOffset() const { return _offset; }
        std::string_view getComment() const { return _comment; }
        ObjectPtr<Track> getTrack() const { return _track; }
        UserId getUserId() const { return _userId; }

        template<class Action>
        void persist(Action& a)
        {
            Wt::Dbo::field(a, _offset, "offset");
            Wt::Dbo::field(a, _comment, "comment");
            Wt::Dbo::field(a, _userId, "user_id");
            Wt::Dbo::belongsTo(a, _track, "track", Wt::Dbo::OnDeleteCascade);
        }

    private:
        friend class Session;
        TrackBookmark(UserId userId, ObjectPtr<Track> track);
        static pointer create(Session& session, UserId userId, ObjectPtr<Track> track);

        static const std::size_t _maxCommentLength = 128;

        std::chrono::duration<int, std::milli> _offset;
        std::string _comment;

        UserId _userId;
        Wt::Dbo::ptr<Track> _track;
    };

} // namespace lms::db
