/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "database/MumaRatingOutbox.hpp"

#include <tuple>

#include <Wt/Dbo/Dbo.h>

#include "database/Session.hpp"

#include "Utils.hpp"

namespace lms::db::mumaRatingOutbox
{
    namespace
    {
        using KeyRow = std::tuple<long long, std::string, std::string, std::string>;

        // Deletes the rows `rows` names and returns their keys, oldest first.
        std::vector<Key> removeRows(Session& session, const std::vector<KeyRow>& rows)
        {
            std::vector<Key> keys;
            keys.reserve(rows.size());
            for (const auto& [id, username, objectType, objectId] : rows)
            {
                utils::executeCommand(*session.getDboSession(), "DELETE FROM muma_rating_outbox WHERE id = ?", id);
                keys.push_back(Key{ .username = username, .objectType = objectType, .objectId = objectId });
            }
            return keys;
        }
    } // namespace

    long long replace(Session& session, const Key& key, std::string_view payload, const Wt::WDateTime& created)
    {
        session.checkWriteTransaction();

        utils::executeCommand(*session.getDboSession(), "DELETE FROM muma_rating_outbox WHERE username = ? AND object_type = ? AND object_id = ?", key.username, key.objectType, key.objectId);
        utils::executeCommand(*session.getDboSession(), "INSERT INTO muma_rating_outbox (username, object_type, object_id, payload, created) VALUES (?, ?, ?, ?, ?)", key.username, key.objectType, key.objectId, std::string{ payload }, static_cast<long long>(created.toTime_t()));
        return session.getDboSession()->query<long long>("SELECT last_insert_rowid()").resultValue();
    }

    std::optional<Entry> front(Session& session)
    {
        session.checkReadTransaction();

        using Row = std::tuple<long long, std::string, std::string, std::string, std::string, long long, long long>;
        const auto rows{ utils::fetchQueryResults(session.getDboSession()->query<Row>("SELECT id, username, object_type, object_id, payload, created, attempts FROM muma_rating_outbox ORDER BY id LIMIT 1")) };
        if (rows.empty())
            return std::nullopt;

        const auto& [id, username, objectType, objectId, payload, created, attempts]{ rows.front() };
        return Entry{
            .id = id,
            .key = Key{ .username = username, .objectType = objectType, .objectId = objectId },
            .payload = payload,
            .created = Wt::WDateTime::fromTime_t(static_cast<std::time_t>(created)),
            .attempts = attempts,
        };
    }

    void remove(Session& session, long long id)
    {
        session.checkWriteTransaction();

        utils::executeCommand(*session.getDboSession(), "DELETE FROM muma_rating_outbox WHERE id = ?", id);
    }

    void recordAttempt(Session& session, long long id)
    {
        session.checkWriteTransaction();

        utils::executeCommand(*session.getDboSession(), "UPDATE muma_rating_outbox SET attempts = attempts + 1 WHERE id = ?", id);
    }

    std::vector<Key> dropOverflow(Session& session, std::size_t maxCount)
    {
        session.checkWriteTransaction();

        const auto count{ static_cast<std::size_t>(session.getDboSession()->query<long long>("SELECT COUNT(*) FROM muma_rating_outbox").resultValue()) };
        if (count <= maxCount)
            return {};

        const auto rows{ utils::fetchQueryResults(session.getDboSession()->query<KeyRow>("SELECT id, username, object_type, object_id FROM muma_rating_outbox ORDER BY id LIMIT ?").bind(static_cast<long long>(count - maxCount))) };
        return removeRows(session, rows);
    }

    std::vector<Key> dropOlderThan(Session& session, const Wt::WDateTime& cutoff)
    {
        session.checkWriteTransaction();

        const auto rows{ utils::fetchQueryResults(session.getDboSession()->query<KeyRow>("SELECT id, username, object_type, object_id FROM muma_rating_outbox WHERE created < ? ORDER BY id").bind(static_cast<long long>(cutoff.toTime_t()))) };
        return removeRows(session, rows);
    }

    Status getStatus(Session& session)
    {
        session.checkReadTransaction();

        using Row = std::tuple<long long, long long>;
        const Row row{ session.getDboSession()->query<Row>("SELECT COUNT(*), COALESCE(MIN(created), 0) FROM muma_rating_outbox").resultValue() };

        Status status;
        status.count = static_cast<std::size_t>(std::get<0>(row));
        if (status.count > 0)
            status.oldest = Wt::WDateTime::fromTime_t(static_cast<std::time_t>(std::get<1>(row)));
        return status;
    }
} // namespace lms::db::mumaRatingOutbox
