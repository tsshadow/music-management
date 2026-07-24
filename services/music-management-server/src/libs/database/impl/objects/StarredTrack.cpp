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

#include "database/objects/StarredTrack.hpp"

#include <Wt/Dbo/Impl.h>
#include <Wt/Dbo/WtSqlTraits.h>

#include "database/Session.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"

#include "Utils.hpp"
#include "traits/IdTypeTraits.hpp"

DBO_INSTANTIATE_TEMPLATES(lms::db::StarredTrack)

namespace lms::db
{
    StarredTrack::StarredTrack(ObjectPtr<Track> track, UserId userId, FeedbackBackend backend)
        : _backend{ backend }
        , _track{ getDboPtr(track) }
        , _userId{ userId }
    {
    }

    StarredTrack::pointer StarredTrack::create(Session& session, ObjectPtr<Track> track, UserId userId, FeedbackBackend backend)
    {
        return session.getDboSession()->add(std::unique_ptr<StarredTrack>{ new StarredTrack{ track, userId, backend } });
    }

    std::size_t StarredTrack::getCount(Session& session)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->query<int>("SELECT COUNT(*) FROM starred_track"));
    }

    StarredTrack::pointer StarredTrack::find(Session& session, StarredTrackId id)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->find<StarredTrack>().where("id = ?").bind(id));
    }

    StarredTrack::pointer StarredTrack::find(Session& session, TrackId trackId, UserId userId)
    {
        session.checkReadTransaction();
        if (auto user = User::find(session, userId))
            return find(session, trackId, userId, user->getFeedbackBackend());
        return {};
    }

    StarredTrack::pointer StarredTrack::find(Session& session, TrackId trackId, UserId userId, FeedbackBackend backend)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->find<StarredTrack>().where("track_id = ?").bind(trackId).where("user_id = ?").bind(userId).where("backend = ?").bind(backend));
    }

    bool StarredTrack::exists(Session& session, TrackId trackId, UserId userId, FeedbackBackend backend)
    {
        return utils::fetchQuerySingleResult(session.getDboSession()->query<int>("SELECT 1 from starred_track").where("track_id = ?").bind(trackId).where("user_id = ?").bind(userId).where("backend = ?").bind(backend));
    }

    RangeResults<StarredTrackId> StarredTrack::find(Session& session, const FindParameters& params)
    {
        session.checkReadTransaction();

        auto query{ session.getDboSession()->query<StarredTrackId>("SELECT DISTINCT s_t.id FROM starred_track s_t") };

        if (params.backend)
            query.where("s_t.backend = ?").bind(*params.backend);
        if (params.syncState)
            query.where("s_t.sync_state = ?").bind(*params.syncState);
        if (params.user.isValid())
            query.where("s_t.user_id = ?").bind(params.user);

        return utils::execRangeQuery<StarredTrackId>(query, params.range);
    }

    void StarredTrack::setDateTime(const Wt::WDateTime& dateTime)
    {
        _dateTime = utils::normalizeDateTime(dateTime);
    }
} // namespace lms::db
