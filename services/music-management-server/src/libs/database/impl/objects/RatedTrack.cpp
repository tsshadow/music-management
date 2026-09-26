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

#include "database/objects/RatedTrack.hpp"

#include <Wt/Dbo/Impl.h>
#include <Wt/Dbo/WtSqlTraits.h>

#include "database/Session.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"

#include "Utils.hpp"
#include "traits/IdTypeTraits.hpp"

DBO_INSTANTIATE_TEMPLATES(lms::db::RatedTrack)

namespace lms::db
{
    RatedTrack::RatedTrack(ObjectPtr<Track> track, UserId userId)
        : _track{ getDboPtr(track) }
        , _userId{ userId }
    {
    }

    RatedTrack::pointer RatedTrack::create(Session& session, ObjectPtr<Track> track, UserId userId)
    {
        return session.getDboSession()->add(std::unique_ptr<RatedTrack>{ new RatedTrack{ track, userId } });
    }

    std::size_t RatedTrack::getCount(Session& session)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->query<int>("SELECT COUNT(*) FROM rated_track"));
    }

    RatedTrack::pointer RatedTrack::find(Session& session, RatedTrackId id)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->find<RatedTrack>().where("id = ?").bind(id));
    }

    RatedTrack::pointer RatedTrack::find(Session& session, TrackId trackId, UserId userId)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->find<RatedTrack>().where("track_id = ?").bind(trackId).where("user_id = ?").bind(userId));
    }

    RatedTrack::pointer RatedTrack::findHighestInWork(Session& session, int workId, UserId userId)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->query<Wt::Dbo::ptr<RatedTrack>>("SELECT r_t FROM rated_track r_t JOIN track t ON t.id = r_t.track_id").where("t.work_id = ?").bind(workId).where("r_t.user_id = ?").bind(userId).orderBy("r_t.rating DESC, r_t.last_updated DESC").limit(1));
    }

    void RatedTrack::find(Session& session, const FindParameters& params, std::function<void(const pointer&)> func)
    {
        session.checkReadTransaction();

        auto query{ session.getDboSession()->query<Wt::Dbo::ptr<RatedTrack>>("SELECT r_t FROM rated_track r_t") };

        if (params.user.isValid())
            query.where("r_t.user_id = ?").bind(params.user);

        utils::forEachQueryRangeResult(query, params.range, func);
    }

    void RatedTrack::setLastUpdated(const Wt::WDateTime& lastUpdated)
    {
        _lastUpdated = utils::normalizeDateTime(lastUpdated);
    }
} // namespace lms::db
