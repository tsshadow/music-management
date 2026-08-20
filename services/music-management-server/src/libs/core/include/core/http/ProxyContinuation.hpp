/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <chrono>
#include <memory>
#include <string>

#include <Wt/Http/Request.h>
#include <Wt/Http/Response.h>

#include "core/http/ClientRequestParameters.hpp"

namespace boost::asio
{
    class io_context;
}

namespace lms::core::http
{
    class IClient;

    struct ProxyAnswer
    {
        int status{};
        std::string contentType;
        std::string body;
    };

    // Forwards a request to another service and parks the Wt response on a continuation while it is
    // in flight, rather than blocking the calling thread until the answer comes back.
    //
    // That distinction is the whole point. A Wt resource handler owns an HTTP server thread for as
    // long as it runs, and there are only as many of those as there are cores. Handlers that sat on
    // a std::future waiting for MuMa could therefore take the entire pool between them, at which
    // point the server stopped answering anything at all -- an unrelated ping included -- until it
    // was restarted.
    //
    // Call it from a handler and return immediately when it returns nullptr: the request has been
    // sent and nothing may be written to the response yet. Wt re-enters the handler once the answer
    // lands, and the call then returns it, so the same code path can write the response out.
    //
    // The answer always arrives, one way or another: MuMa's own status (whatever it is, including
    // 404), 502 if the request could not be delivered, or 504 once `deadline` passes.
    std::shared_ptr<const ProxyAnswer> proxyRequest(const Wt::Http::Request& request, Wt::Http::Response& response,
        boost::asio::io_context& ioContext, IClient& client, ClientGETRequestParameters&& params, std::chrono::seconds deadline);

    std::shared_ptr<const ProxyAnswer> proxyRequest(const Wt::Http::Request& request, Wt::Http::Response& response,
        boost::asio::io_context& ioContext, IClient& client, ClientPOSTRequestParameters&& params, std::chrono::seconds deadline);
} // namespace lms::core::http
