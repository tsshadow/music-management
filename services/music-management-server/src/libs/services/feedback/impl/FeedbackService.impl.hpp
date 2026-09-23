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

#include "core/ILogger.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/RatedArtist.hpp"
#include "database/objects/RatedRelease.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"
#include "services/feedback/IFeedbackService.hpp"

namespace lms::feedback
{
    using namespace db;

    namespace detail
    {
        /// Login name of \p userId, or an empty string when the user no longer exists.
        inline std::string getLoginName(Session& session, UserId userId)
        {
            const User::pointer user{ User::find(session, userId) };
            return user ? std::string{ user->getLoginName() } : std::string{};
        }

        /// Captures the "rating removed" payload of an artist rating that is about to be deleted.
        inline RatingRemovedEvent makeRatingRemovedEvent(Session& session, const RatedArtist::pointer& ratedArtist)
        {
            RatingRemovedEvent event{ .objectType = "artist", .previousRating = ratedArtist->getRating() };
            if (const auto artist{ ratedArtist->getArtist() })
                event.objectId = artist->getName();
            event.username = getLoginName(session, ratedArtist->getUserId());
            return event;
        }

        /// Captures the "rating removed" payload of a release rating that is about to be deleted.
        inline RatingRemovedEvent makeRatingRemovedEvent(Session& session, const RatedRelease::pointer& ratedRelease)
        {
            RatingRemovedEvent event{ .objectType = "release", .previousRating = ratedRelease->getRating() };
            if (const auto release{ ratedRelease->getRelease() })
                event.objectId = release->getName();
            event.username = getLoginName(session, ratedRelease->getUserId());
            return event;
        }

        /// Captures the "rating removed" payload of a track rating that is about to be deleted.
        inline RatingRemovedEvent makeRatingRemovedEvent(Session& session, const RatedTrack::pointer& ratedTrack)
        {
            RatingRemovedEvent event{ .objectType = "track", .previousRating = ratedTrack->getRating() };
            if (const auto track{ ratedTrack->getTrack() })
            {
                event.objectId = track->getId().toString();
                event.path = track->getAbsoluteFilePath().string();
            }
            event.username = getLoginName(session, ratedTrack->getUserId());
            return event;
        }
    } // namespace detail

    template<typename ObjType, typename ObjIdType, typename StarredObjType>
    void FeedbackService::star(UserId userId, ObjIdType objId)
    {
        const auto backend{ getUserFeedbackBackend(userId) };
        if (!backend)
            return;

        typename StarredObjType::IdType starredObjId;
        {
            Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };

            typename StarredObjType::pointer starredObj{ StarredObjType::find(session, objId, userId, *backend) };
            if (!starredObj)
            {
                const typename ObjType::pointer obj{ ObjType::find(session, objId) };
                if (!obj)
                    return;

                const User::pointer user{ User::find(session, userId) };
                if (!user)
                    return;

                starredObj = session.create<StarredObjType>(obj, user, *backend);
            }
            starredObj.modify()->setDateTime(Wt::WDateTime::currentDateTime());
            starredObjId = starredObj->getId();
        }
        if (auto* backendImpl{ findBackend(*backend) })
            backendImpl->onStarred(starredObjId);
    }

    template<typename ObjType, typename ObjIdType, typename StarredObjType>
    void FeedbackService::unstar(UserId userId, ObjIdType objId)
    {
        const auto backend{ getUserFeedbackBackend(userId) };
        if (!backend)
            return;

        typename StarredObjType::IdType starredObjId;
        {
            Session& session{ _db.getTLSSession() };
            auto transaction{ session.createReadTransaction() };

            typename StarredObjType::pointer starredObj{ StarredObjType::find(session, objId, userId, *backend) };
            if (!starredObj)
                return;

            starredObjId = starredObj->getId();
        }
        if (auto* backendImpl{ findBackend(*backend) })
            backendImpl->onUnstarred(starredObjId);
    }

    template<typename ObjType, typename ObjIdType, typename RatedObjType>
    bool FeedbackService::isFavorite(UserId userId, ObjIdType objId)
    {
        Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        const typename RatedObjType::pointer ratedObj{ RatedObjType::find(session, objId, userId) };
        return ratedObj && ratedObj->getRating() >= favoriteRating;
    }

    template<typename ObjType, typename ObjIdType, typename RatedObjType>
    Wt::WDateTime FeedbackService::getFavoriteDateTime(UserId userId, ObjIdType objId)
    {
        // Nothing records when something became a favorite as such: the moment the
        // rating was last changed is the closest thing we have, and it is what the
        // Subsonic "starred" attribute is filled with.
        Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        const typename RatedObjType::pointer ratedObj{ RatedObjType::find(session, objId, userId) };
        if (ratedObj && ratedObj->getRating() >= favoriteRating)
            return ratedObj->getLastUpdated();

        return {};
    }

    template<typename ObjType, typename ObjIdType, typename RatedObjType>
    void FeedbackService::setRating(db::UserId userId, ObjIdType objectId, std::optional<db::Rating> rating)
    {
        const auto backend{ getUserFeedbackBackend(userId) };
        if (!backend)
            return;

        typename RatedObjType::IdType ratedObjectId;
        std::optional<RatingRemovedEvent> removedEvent;
        {
            Session& session{ _db.getTLSSession() };
            auto transaction{ session.createWriteTransaction() };

            typename RatedObjType::pointer ratedObject{ RatedObjType::find(session, objectId, userId) };
            if (rating)
            {
                if (!ratedObject)
                {
                    typename ObjType::pointer obj{ ObjType::find(session, objectId) };
                    const User::pointer user{ User::find(session, userId) };

                    if (!obj || !user)
                        return;

                    ratedObject = session.create<RatedObjType>(obj, user);
                }

                ratedObject.modify()->setRating(*rating);
                ratedObject.modify()->setLastUpdated(Wt::WDateTime::currentDateTime());
                ratedObjectId = ratedObject->getId();
            }
            else
            {
                if (ratedObject)
                {
                    // Capture the payload now: once the row is removed, a backend that looks
                    // it up by id finds nothing and the removal is never reported.
                    removedEvent = detail::makeRatingRemovedEvent(session, ratedObject);
                    ratedObject.remove();
                }
            }
        }

        IFeedbackBackend* backendImpl{ findBackend(*backend) };
        if (!backendImpl)
            return;

        if (removedEvent)
            backendImpl->onRatingRemoved(*removedEvent);
        else if (ratedObjectId.isValid())
            backendImpl->onRatingChanged(ratedObjectId);
    }

    template<typename ObjType, typename ObjIdType, typename RatedObjType>
    std::optional<db::Rating> FeedbackService::getRating(db::UserId userId, ObjIdType objectId)
    {
        Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        const typename RatedObjType::pointer ratedObj{ RatedObjType::find(session, objectId, userId) };
        if (!ratedObj)
            return std::nullopt;

        return ratedObj->getRating();
    }

} // namespace lms::feedback
