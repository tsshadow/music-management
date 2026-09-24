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

#include "FeedbackService.hpp"
#include "FeedbackService.impl.hpp"

#include "core/ILogger.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/RatedArtist.hpp"
#include "database/objects/RatedRelease.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/StarredArtist.hpp"
#include "database/objects/StarredRelease.hpp"
#include "database/objects/StarredTrack.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"

#include "internal/InternalBackend.hpp"
#include "listenbrainz/ListenBrainzBackend.hpp"
#include "musicmanagement/MusicManagementBackend.hpp"

namespace lms::feedback
{
    std::unique_ptr<IFeedbackService> createFeedbackService(boost::asio::io_context& ioContext, db::IDb& db)
    {
        return std::make_unique<FeedbackService>(ioContext, db);
    }

    FeedbackService::FeedbackService(boost::asio::io_context& ioContext, db::IDb& db)
        : _db{ db }
    {
        LMS_LOG(SCROBBLING, INFO, "Starting service...");
        _backends.emplace(db::FeedbackBackend::Internal, std::make_unique<InternalBackend>(_db));
        _backends.emplace(db::FeedbackBackend::ListenBrainz, std::make_unique<listenBrainz::ListenBrainzBackend>(ioContext, _db));
        _backends.emplace(db::FeedbackBackend::MusicManagement, std::make_unique<musicManagement::MusicManagementBackend>(ioContext, _db));
        LMS_LOG(SCROBBLING, INFO, "Service started!");
    }

    FeedbackService::FeedbackService(db::IDb& db, Backends backends)
        : _db{ db }
        , _backends{ std::move(backends) }
    {
    }

    FeedbackService::~FeedbackService()
    {
        LMS_LOG(SCROBBLING, INFO, "Service stopped!");
    }

    std::optional<db::FeedbackBackend> FeedbackService::getUserFeedbackBackend(db::UserId userId)
    {
        std::optional<db::FeedbackBackend> feedbackBackend;

        Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };
        if (const User::pointer user{ User::find(session, userId) })
            feedbackBackend = user->getFeedbackBackend();

        return feedbackBackend;
    }

    IFeedbackBackend* FeedbackService::findBackend(db::FeedbackBackend backend) const
    {
        const auto it{ _backends.find(backend) };
        if (it == std::cend(_backends) || !it->second)
        {
            LMS_LOG(SCROBBLING, WARNING, "No feedback backend registered for value " << static_cast<int>(backend) << ", event skipped");
            return nullptr;
        }
        return it->second.get();
    }

    void FeedbackService::star(UserId userId, ArtistId artistId)
    {
        star<Artist, ArtistId, StarredArtist>(userId, artistId);
    }

    void FeedbackService::unstar(UserId userId, ArtistId artistId)
    {
        unstar<Artist, ArtistId, StarredArtist>(userId, artistId);
    }

    bool FeedbackService::isFavorite(UserId userId, ArtistId artistId)
    {
        return isFavorite<Artist, ArtistId, RatedArtist>(userId, artistId);
    }

    Wt::WDateTime FeedbackService::getFavoriteDateTime(UserId userId, ArtistId artistId)
    {
        return getFavoriteDateTime<Artist, ArtistId, RatedArtist>(userId, artistId);
    }

    FeedbackService::ArtistContainer FeedbackService::findFavoriteArtists(const ArtistFindParameters& params)
    {
        Artist::FindParameters searchParams;
        searchParams.setFilters(params.filters);
        searchParams.setRatingUser(params.user, favoriteRating);
        searchParams.setKeywords(params.keywords);
        searchParams.setTrackArtistLinkType(params.trackArtistLinkType);
        searchParams.setSortMethod(params.sortMethod == ArtistSortMethod::StarredDateDesc ? ArtistSortMethod::RatedDateDesc : params.sortMethod);
        searchParams.setRange(params.range);

        Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        return Artist::findIds(session, searchParams);
    }

    void FeedbackService::setRating(db::UserId userId, db::ArtistId artistId, std::optional<db::Rating> rating)
    {
        setRating<Artist, ArtistId, RatedArtist>(userId, artistId, rating);
    }

    std::optional<db::Rating> FeedbackService::getRating(db::UserId userId, db::ArtistId artistId)
    {
        return getRating<Artist, ArtistId, RatedArtist>(userId, artistId);
    }

    void FeedbackService::star(UserId userId, ReleaseId releaseId)
    {
        star<Release, ReleaseId, StarredRelease>(userId, releaseId);
    }

    void FeedbackService::unstar(UserId userId, ReleaseId releaseId)
    {
        unstar<Release, ReleaseId, StarredRelease>(userId, releaseId);
    }

    bool FeedbackService::isFavorite(UserId userId, ReleaseId releaseId)
    {
        return isFavorite<Release, ReleaseId, RatedRelease>(userId, releaseId);
    }

    Wt::WDateTime FeedbackService::getFavoriteDateTime(UserId userId, ReleaseId releaseId)
    {
        return getFavoriteDateTime<Release, ReleaseId, RatedRelease>(userId, releaseId);
    }

    FeedbackService::ReleaseContainer FeedbackService::findFavoriteReleases(const FindParameters& params)
    {
        Release::FindParameters searchParams;
        searchParams.setRatingUser(params.user, favoriteRating);
        searchParams.setFilters(params.filters);
        searchParams.setKeywords(params.keywords);
        searchParams.setSortMethod(ReleaseSortMethod::RatedDateDesc);
        searchParams.setRange(params.range);

        Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        return Release::findIds(session, searchParams);
    }

    void FeedbackService::setRating(db::UserId userId, db::ReleaseId releaseId, std::optional<db::Rating> rating)
    {
        setRating<Release, ReleaseId, RatedRelease>(userId, releaseId, rating);
    }

    std::optional<db::Rating> FeedbackService::getRating(db::UserId userId, db::ReleaseId releaseId)
    {
        return getRating<Release, ReleaseId, RatedRelease>(userId, releaseId);
    }

    void FeedbackService::star(UserId userId, TrackId trackId)
    {
        star<Track, TrackId, StarredTrack>(userId, trackId);
    }

    void FeedbackService::unstar(UserId userId, TrackId trackId)
    {
        unstar<Track, TrackId, StarredTrack>(userId, trackId);
    }

    bool FeedbackService::isFavorite(UserId userId, TrackId trackId)
    {
        return isFavorite<Track, TrackId, RatedTrack>(userId, trackId);
    }

    Wt::WDateTime FeedbackService::getFavoriteDateTime(UserId userId, TrackId trackId)
    {
        return getFavoriteDateTime<Track, TrackId, RatedTrack>(userId, trackId);
    }

    FeedbackService::TrackContainer FeedbackService::findFavoriteTracks(const FindParameters& params)
    {
        Track::FindParameters searchParams;
        searchParams.ratingUser = params.user;
        searchParams.setMinRating(favoriteRating);
        searchParams.setFilters(params.filters);
        searchParams.setKeywords(params.keywords);
        searchParams.setSortMethod(TrackSortMethod::RatedDateDesc);
        searchParams.setRange(params.range);

        Session& session{ _db.getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        return Track::findIds(session, searchParams);
    }

    void FeedbackService::setRating(db::UserId userId, db::TrackId trackId, std::optional<db::Rating> rating)
    {
        setRating<db::Track, db::TrackId, db::RatedTrack>(userId, trackId, rating);
    }

    std::optional<db::Rating> FeedbackService::getRating(db::UserId userId, db::TrackId trackId)
    {
        return getRating<db::Track, db::TrackId, db::RatedTrack>(userId, trackId);
    }

    void FeedbackService::notifyPlaylistChanged(db::TrackListId playlistId)
    {
        for (auto& [backendType, backend] : _backends)
            backend->onPlaylistChanged(playlistId);
    }
} // namespace lms::feedback
