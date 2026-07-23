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

#include "database/objects/StarredArtist.hpp"

#include <Wt/Dbo/Impl.h>
#include <Wt/Dbo/WtSqlTraits.h>

#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/User.hpp"

#include "Utils.hpp"
#include "traits/IdTypeTraits.hpp"

DBO_INSTANTIATE_TEMPLATES(lms::db::StarredArtist)

namespace lms::db
{
    StarredArtist::StarredArtist(ObjectPtr<Artist> artist, UserId userId, FeedbackBackend backend)
        : _backend{ backend }
        , _artist{ getDboPtr(artist) }
        , _userId{ userId }
    {
    }

    StarredArtist::pointer StarredArtist::create(Session& session, ObjectPtr<Artist> artist, UserId userId, FeedbackBackend backend)
    {
        return session.getDboSession()->add(std::unique_ptr<StarredArtist>{ new StarredArtist{ artist, userId, backend } });
    }

    std::size_t StarredArtist::getCount(Session& session)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->query<int>("SELECT COUNT(*) FROM starred_artist"));
    }

    StarredArtist::pointer StarredArtist::find(Session& session, StarredArtistId id)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->find<StarredArtist>().where("id = ?").bind(id));
    }

    StarredArtist::pointer StarredArtist::find(Session& session, ArtistId artistId, UserId userId)
    {
        session.checkReadTransaction();
        if (auto user = User::find(session, userId))
            return find(session, artistId, userId, user->getFeedbackBackend());
        return {};
    }

    StarredArtist::pointer StarredArtist::find(Session& session, ArtistId artistId, UserId userId, FeedbackBackend backend)
    {
        session.checkReadTransaction();
        return utils::fetchQuerySingleResult(session.getDboSession()->find<StarredArtist>().where("artist_id = ?").bind(artistId).where("user_id = ?").bind(userId).where("backend = ?").bind(backend));
    }

    void StarredArtist::setDateTime(const Wt::WDateTime& dateTime)
    {
        _dateTime = utils::normalizeDateTime(dateTime);
    }
} // namespace lms::db
