/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "core/http/ProxyContinuation.hpp"

#include <atomic>
#include <utility>

#include <boost/asio/steady_timer.hpp>

#include "core/http/IClient.hpp"

namespace lms::core::http
{
    namespace
    {
        // Carries one proxied request across the two passes of its continuation.
        struct ProxyState
        {
            std::atomic<bool> settled{};
            ProxyAnswer answer;
            std::unique_ptr<boost::asio::steady_timer> deadline;
        };

        std::shared_ptr<const ProxyAnswer> takeAnswer(Wt::Http::ResponseContinuation& continuation)
        {
            const auto state{ Wt::cpp17::any_cast<std::shared_ptr<ProxyState>>(continuation.data()) };

            // Aliasing: hands out the answer while the state that owns it stays alive.
            return std::shared_ptr<const ProxyAnswer>{ state, &state->answer };
        }

        template<typename Params>
        void fillCallbacks(Params& params, const std::shared_ptr<ProxyState>& state, Wt::Http::ResponseContinuation* continuation)
        {
            // Whichever gets there first -- the answer, a delivery failure, or the deadline --
            // settles the request; the others find it settled and do nothing.
            auto settle = [state, continuation](int status, std::string contentType, std::string body) {
                if (state->settled.exchange(true))
                    return;

                state->answer.status = status;
                state->answer.contentType = std::move(contentType);
                state->answer.body = std::move(body);

                boost::system::error_code ignored;
                state->deadline->cancel(ignored);

                continuation->haveMoreData();
            };

            // The caller decides what a non-200 means, so every status it gets is its own.
            params.treatAnyStatusAsSuccess = true;

            params.onSuccessFunc = [settle](const Wt::Http::Message& msg) {
                std::string contentType;
                if (const std::string* header{ msg.getHeader("Content-Type") })
                    contentType = *header;

                settle(msg.status(), std::move(contentType), msg.body());
            };

            params.onFailureFunc = [settle]() {
                settle(502, {}, {}); // Bad Gateway
            };
        }

        template<typename Params, typename SendFunc>
        std::shared_ptr<const ProxyAnswer> proxy(const Wt::Http::Request& request, Wt::Http::Response& response,
                                                 boost::asio::io_context& ioContext, Params&& params, std::chrono::seconds deadline, SendFunc&& send)
        {
            if (Wt::Http::ResponseContinuation * continuation{ request.continuation() })
                return takeAnswer(*continuation);

            auto state{ std::make_shared<ProxyState>() };

            // Nothing has been written to the response yet, so its status and mime type are still
            // free to be set on the way back in.
            Wt::Http::ResponseContinuation* continuation{ response.createContinuation() };
            continuation->setData(state);
            continuation->waitForMoreData();

            fillCallbacks(params, state, continuation);

            // The send queue retries and backs off, so an answer is bounded but not promptly
            // bounded. Without this, one request MuMa never answers holds a connection open for
            // minutes.
            state->deadline = std::make_unique<boost::asio::steady_timer>(ioContext);
            state->deadline->expires_after(deadline);
            state->deadline->async_wait([state, continuation](const boost::system::error_code& ec) {
                if (ec == boost::asio::error::operation_aborted)
                    return;

                if (state->settled.exchange(true))
                    return;

                state->answer.status = 504; // Gateway Timeout
                continuation->haveMoreData();
            });

            send(std::move(params));

            return nullptr;
        }
    } // namespace

    std::shared_ptr<const ProxyAnswer> proxyRequest(const Wt::Http::Request& request, Wt::Http::Response& response,
                                                    boost::asio::io_context& ioContext, IClient& client, ClientGETRequestParameters&& params, std::chrono::seconds deadline)
    {
        return proxy(request, response, ioContext, std::move(params), deadline,
                     [&client](ClientGETRequestParameters&& p) { client.sendGETRequest(std::move(p)); });
    }

    std::shared_ptr<const ProxyAnswer> proxyRequest(const Wt::Http::Request& request, Wt::Http::Response& response,
                                                    boost::asio::io_context& ioContext, IClient& client, ClientPOSTRequestParameters&& params, std::chrono::seconds deadline)
    {
        return proxy(request, response, ioContext, std::move(params), deadline,
                     [&client](ClientPOSTRequestParameters&& p) { client.sendPOSTRequest(std::move(p)); });
    }
} // namespace lms::core::http
