/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "database/MumaListenOutbox.hpp"

#include <tuple>

#include <Wt/Dbo/Dbo.h>

#include "database/Session.hpp"

#include "Utils.hpp"

namespace lms::db::mumaListenOutbox
{
    namespace
    {
        // Rows changed by the last statement on this connection.
        std::size_t lastChangeCount(Session& session)
        {
            return static_cast<std::size_t>(session.getDboSession()->query<long long>("SELECT changes()").resultValue());
        }
    } // namespace

    long long push(Session& session, std::string_view payload, const Wt::WDateTime& created)
    {
        session.checkWriteTransaction();

        utils::executeCommand(*session.getDboSession(), "INSERT INTO muma_listen_outbox (payload, created) VALUES (?, ?)", std::string{ payload }, static_cast<long long>(created.toTime_t()));
        return session.getDboSession()->query<long long>("SELECT last_insert_rowid()").resultValue();
    }

    std::optional<Entry> front(Session& session)
    {
        session.checkReadTransaction();

        using Row = std::tuple<long long, std::string, long long, long long>;
        const auto rows{ utils::fetchQueryResults(session.getDboSession()->query<Row>("SELECT id, payload, created, attempts FROM muma_listen_outbox ORDER BY id LIMIT 1")) };
        if (rows.empty())
            return std::nullopt;

        const auto& [id, payload, created, attempts]{ rows.front() };
        return Entry{ .id = id, .payload = payload, .created = Wt::WDateTime::fromTime_t(static_cast<std::time_t>(created)), .attempts = attempts };
    }

    void remove(Session& session, long long id)
    {
        session.checkWriteTransaction();

        utils::executeCommand(*session.getDboSession(), "DELETE FROM muma_listen_outbox WHERE id = ?", id);
    }

    void recordAttempt(Session& session, long long id)
    {
        session.checkWriteTransaction();

        utils::executeCommand(*session.getDboSession(), "UPDATE muma_listen_outbox SET attempts = attempts + 1 WHERE id = ?", id);
    }

    std::size_t dropOverflow(Session& session, std::size_t maxCount)
    {
        session.checkWriteTransaction();

        const auto count{ static_cast<std::size_t>(session.getDboSession()->query<long long>("SELECT COUNT(*) FROM muma_listen_outbox").resultValue()) };
        if (count <= maxCount)
            return 0;

        utils::executeCommand(*session.getDboSession(), "DELETE FROM muma_listen_outbox WHERE id IN (SELECT id FROM muma_listen_outbox ORDER BY id LIMIT ?)", static_cast<long long>(count - maxCount));
        return lastChangeCount(session);
    }

    std::size_t dropOlderThan(Session& session, const Wt::WDateTime& cutoff)
    {
        session.checkWriteTransaction();

        utils::executeCommand(*session.getDboSession(), "DELETE FROM muma_listen_outbox WHERE created < ?", static_cast<long long>(cutoff.toTime_t()));
        return lastChangeCount(session);
    }

    Status getStatus(Session& session)
    {
        session.checkReadTransaction();

        using Row = std::tuple<long long, long long>;
        const Row row{ session.getDboSession()->query<Row>("SELECT COUNT(*), COALESCE(MIN(created), 0) FROM muma_listen_outbox").resultValue() };

        Status status;
        status.count = static_cast<std::size_t>(std::get<0>(row));
        if (status.count > 0)
            status.oldest = Wt::WDateTime::fromTime_t(static_cast<std::time_t>(std::get<1>(row)));
        return status;
    }
} // namespace lms::db::mumaListenOutbox
