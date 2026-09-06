/*
 * Copyright (C) 2025 Emeric Poupon
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

#include "database/objects/ArtistInfo.hpp"

#include <Wt/Dbo/Impl.h>
#include <Wt/Dbo/WtSqlTraits.h>

#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/ArtistInfoId.hpp"
#include "database/objects/Directory.hpp"

#include "Utils.hpp"
#include "traits/IdTypeTraits.hpp"
#include "traits/PathTraits.hpp"

DBO_INSTANTIATE_TEMPLATES(lms::db::ArtistInfo)

namespace lms::db
{
    ArtistInfo::pointer ArtistInfo::create(Session& session)
    {
        return session.getDboSession()->add(std::unique_ptr<ArtistInfo>{ new ArtistInfo{} });
    }

    std::size_t ArtistInfo::getCount(Session& session)
    {
        session.checkReadTransaction();

        return utils::fetchQuerySingleResult(session.getDboSession()->query<int>("SELECT COUNT(*) FROM artist_info"));
    }

    ArtistInfo::pointer ArtistInfo::find(Session& session, const std::filesystem::path& p)
    {
        session.checkReadTransaction();

        return utils::fetchQuerySingleResult(session.getDboSession()->query<Wt::Dbo::ptr<ArtistInfo>>("SELECT a_i from artist_info a_i").where("a_i.absolute_file_path = ?").bind(p));
    }

    ArtistInfo::pointer ArtistInfo::find(Session& session, ArtistInfoId id)
    {
        session.checkReadTransaction();

        return utils::fetchQuerySingleResult(session.getDboSession()->query<Wt::Dbo::ptr<ArtistInfo>>("SELECT a_i from artist_info a_i").where("a_i.id = ?").bind(id));
    }

    void ArtistInfo::find(Session& session, ArtistId id, std::optional<Range> range, const std::function<void(const pointer&)>& func)
    {
        session.checkReadTransaction();

        auto query{ session.getDboSession()->query<Wt::Dbo::ptr<ArtistInfo>>("SELECT a_i from artist_info a_i").where("a_i.artist_id = ?").bind(id) };
        utils::forEachQueryRangeResult(query, range, [&](const ArtistInfo::pointer& entry) {
            func(entry);
        });
    }

    void ArtistInfo::find(Session& session, ArtistId id, const std::function<void(const pointer&)>& func)
    {
        find(session, id, std::nullopt, func);
    }

    void ArtistInfo::find(Session& session, ArtistInfoId& lastRetrievedId, std::size_t count, const std::function<void(const pointer&)>& func)
    {
        session.checkReadTransaction();

        auto query{ session.getDboSession()->query<Wt::Dbo::ptr<ArtistInfo>>("SELECT a_i from artist_info a_i").orderBy("a_i.id").where("a_i.id > ?").bind(lastRetrievedId).limit(static_cast<int>(count)) };

        utils::forEachQueryResult(query, [&](const ArtistInfo::pointer& entry) {
            func(entry);
            lastRetrievedId = entry->getId();
        });
    }

    void ArtistInfo::findArtistNameNoLongerMatch(Session& session, std::optional<Range> range, const std::function<void(const pointer&)>& func)
    {
        session.checkReadTransaction();

        auto query{ session.getDboSession()->query<Wt::Dbo::ptr<ArtistInfo>>("SELECT a_i FROM artist_info a_i") };
        query.join("artist a ON a_i.artist_id = a.id");
        query.where("a_i.mbid_matched = FALSE");
        query.where("a_i.name <> a.name");

        utils::applyRange(query, range);
        utils::forEachQueryResult(query, [&](const pointer& info) {
            func(info);
        });
    }

    void ArtistInfo::findWithArtistNameAmbiguity(Session& session, std::optional<Range> range, bool allowArtistMBIDFallback, const std::function<void(const pointer&)>& func)
    {
        session.checkReadTransaction();

        auto query{ session.getDboSession()->query<Wt::Dbo::ptr<ArtistInfo>>("SELECT a_i FROM artist_info a_i") };
        query.join("artist a ON a_i.artist_id = a.id");
        query.where("a_i.mbid_matched = FALSE");
        if (!allowArtistMBIDFallback)
        {
            query.where("a.mbid <> ''");
        }
        else
        {
            query.where(R"(
                (a.mbid <> '' AND EXISTS (SELECT 1 FROM artist a2 WHERE a2.name = a.name AND a2.mbid <> '' AND a2.mbid <> a.mbid))
                OR (a.mbid = '' AND (SELECT COUNT(*) FROM artist a2 WHERE a2.name = a.name AND a2.mbid <> '') = 1))");
        }

        utils::applyRange(query, range);
        utils::forEachQueryResult(query, [&](const pointer& info) {
            func(info);
        });
    }

    void ArtistInfo::findAbsoluteFilePath(Session& session, ArtistInfoId& lastRetrievedId, std::size_t count, const std::function<void(ArtistInfoId artistInfoId, const std::filesystem::path& absoluteFilePath)>& func)
    {
        session.checkReadTransaction();

        auto query{ session.getDboSession()->query<std::tuple<ArtistInfoId, std::filesystem::path>>("SELECT a_i.id, a_i.absolute_file_path FROM artist_info a_i").orderBy("a_i.id").where("a_i.id > ?").bind(lastRetrievedId).limit(static_cast<int>(count)) };

        utils::forEachQueryResult(query, [&](const auto& res) {
            func(std::get<0>(res), std::get<1>(res));
            lastRetrievedId = std::get<0>(res);
        });
    }

    // Same keyset walk as findAbsoluteFilePath, restricted to the files under one directory.
    //
    // The bound is a half-open byte range rather than a LIKE pattern, for two reasons that
    // both bite silently. SQLite's LIKE is case-insensitive for ASCII unless
    // case_sensitive_like is set, so '/music/eps/...' would match a genuinely different
    // directory on a case-sensitive filesystem. And a prefix match on the bare directory
    // name matches its siblings: '/music/A' would pull in everything under '/music/AB'.
    // '/' is 0x2F and '0' is 0x30, so [dir + '/', dir + '0') is exactly "under dir/".
    //
    // The ORDER BY stays on the id, so this is still an index walk over the whole table with
    // the range applied as a filter. What collapses is the work per returned row: the caller
    // stat()s every path it gets back, and that is where the minutes go.
    void ArtistInfo::findAbsoluteFilePathInDirectory(Session& session, ArtistInfoId& lastRetrievedId, std::size_t count, const std::filesystem::path& directory, const std::function<void(ArtistInfoId artistInfoId, const std::filesystem::path& absoluteFilePath)>& func)
    {
        session.checkReadTransaction();

        const std::string lowerBound{ (directory / "").string() }; // trailing separator, idempotent
        std::string upperBound{ lowerBound };
        upperBound.back() = static_cast<char>(upperBound.back() + 1);

        auto query{ session.getDboSession()->query<std::tuple<ArtistInfoId, std::filesystem::path>>("SELECT a_i.id, a_i.absolute_file_path FROM artist_info a_i").orderBy("a_i.id").where("a_i.id > ?").bind(lastRetrievedId).where("a_i.absolute_file_path >= ?").bind(lowerBound).where("a_i.absolute_file_path < ?").bind(upperBound).limit(static_cast<int>(count)) };

        utils::forEachQueryResult(query, [&](const auto& res) {
            func(std::get<0>(res), std::get<1>(res));
            lastRetrievedId = std::get<0>(res);
        });
    }

    Artist::pointer ArtistInfo::getArtist() const
    {
        return _artist;
    }

    Directory::pointer ArtistInfo::getDirectory() const
    {
        return _directory;
    }

    void ArtistInfo::setAbsoluteFilePath(const std::filesystem::path& filePath)
    {
        assert(filePath.is_absolute());
        _absoluteFilePath = filePath;
        _fileStem = filePath.stem();
    }

    void ArtistInfo::setDirectory(ObjectPtr<Directory> directory)
    {
        _directory = getDboPtr(directory);
    }

    void ArtistInfo::setArtist(ObjectPtr<Artist> artist)
    {
        _artist = getDboPtr(artist);
    }
} // namespace lms::db
