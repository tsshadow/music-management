/*
 * Copyright (C) 2024 Emeric Poupon
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

#include <optional>

#include <Wt/Dbo/Field.h>
#include <Wt/WDateTime.h>

#include "database/Object.hpp"
#include "database/Types.hpp"
#include "database/objects/RatedTrackId.hpp"
#include "database/objects/TrackId.hpp"
#include "database/objects/Types.hpp"
#include "database/objects/UserId.hpp"

namespace lms::db
{
    class Track;
    class Session;
    class User;

    class RatedTrack final : public Object<RatedTrack, RatedTrackId>
    {
    public:
        RatedTrack() = default;

        struct FindParameters
        {
            UserId user; // and this user
            std::optional<Range> range;

            FindParameters& setUser(UserId _user)
            {
                user = _user;
                return *this;
            }
            FindParameters& setRange(std::optional<Range> _range)
            {
                range = _range;
                return *this;
            }
        };

        // Search utility
        static std::size_t getCount(Session& session);
        static pointer find(Session& session, RatedTrackId id);
        static pointer find(Session& session, TrackId trackId, UserId userId);
        static void find(Session& session, const FindParameters& findParams, std::function<void(const pointer&)> func);
        //: The rating a song shows: the highest this user gave any version of work `workId`
        //: (the most recent of those on a tie), or null when no version is rated. Ratings stay
        //: stored per file -- this is the display roll-up of the song-versions design.
        static pointer findHighestInWork(Session& session, int workId, UserId userId);

        // Accessors
        ObjectPtr<Track> getTrack() const { return _track; }
        UserId getUserId() const { return _userId; }
        Rating getRating() const { return _rating; }
        const Wt::WDateTime& getLastUpdated() const { return _lastUpdated; }

        // Setters
        void setRating(Rating rating) { _rating = rating; }
        void setLastUpdated(const Wt::WDateTime& lastUpdated);

        template<class Action>
        void persist(Action& a)
        {
            Wt::Dbo::field(a, _rating, "rating");
            Wt::Dbo::field(a, _lastUpdated, "last_updated");
            Wt::Dbo::field(a, _userId, "user_id");

            Wt::Dbo::belongsTo(a, _track, "track", Wt::Dbo::OnDeleteCascade);
        }

    private:
        friend class Session;
        RatedTrack(ObjectPtr<Track> track, UserId userId);
        static pointer create(Session& session, ObjectPtr<Track> track, UserId userId);

        Rating _rating{};
        Wt::WDateTime _lastUpdated; // when it was rated for the last time

        Wt::Dbo::ptr<Track> _track;
        UserId _userId;
    };
} // namespace lms::db
