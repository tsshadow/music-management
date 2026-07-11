#pragma once

#include <boost/asio/io_context.hpp>
#include <Wt/WResource.h>
#include "database/IDb.hpp"
#include "core/http/IClient.hpp"

namespace lms::api::muma
{
    class MumaResource : public Wt::WResource
    {
    public:
        MumaResource(boost::asio::io_context& ioContext, db::IDb& db);
        ~MumaResource();

        void handleRequest(const Wt::Http::Request& request, Wt::Http::Response& response) override;

    private:
        db::IDb& _db;
        std::unique_ptr<core::http::IClient> _httpClient;
        std::string _mumaApiUrl;
        std::string _mumaApiKey;
    };
}
