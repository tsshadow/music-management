/*
 * Copyright (C) 2024 Junie
 *
 * This file is part of LMS.
 */

#pragma once

#include <boost/asio/io_context.hpp>
#include <memory>
#include <string>

#include "IScrobblingBackend.hpp"
#include "core/http/IClient.hpp"

namespace lms::db
{
    class IDb;
}

namespace lms::scrobbling::musicManagement
{
    class MusicManagementBackend final : public IScrobblingBackend
    {
    public:
        MusicManagementBackend(boost::asio::io_context& ioContext, db::IDb& db);
        ~MusicManagementBackend() override;

    private:
        MusicManagementBackend(const MusicManagementBackend&) = delete;
        MusicManagementBackend& operator=(const MusicManagementBackend&) = delete;

        void listenStarted(const Listen& listen) override;
        void listenFinished(const Listen& listen, std::optional<std::chrono::seconds> duration) override;
        void addTimedListen(const TimedListen& listen) override;

        void sendScrobble(const Listen& listen, const Wt::WDateTime& timePoint, std::optional<std::chrono::seconds> duration = std::nullopt);

        boost::asio::io_context& _ioContext;
        db::IDb& _db;
        std::string _apiUrl;
        std::string _apiKey;
        std::unique_ptr<core::http::IClient> _client;
    };
} // namespace lms::scrobbling::musicManagement
