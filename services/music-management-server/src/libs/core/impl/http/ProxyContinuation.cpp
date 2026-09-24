/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "core/http/ProxyContinuation.hpp"

#include <utility>

#include <Wt/Http/ResponseContinuation.h>

#include "core/http/IClient.hpp"

#include "ProxyState.hpp"

namespace lms::core::http
{
    namespace
    {
        using State = detail::ProxyState<Wt::Http::ResponseContinuation>;

        std::shared_ptr<const ProxyAnswer> takeAnswer(Wt::Http::ResponseContinuation& continuation)
        {
            const auto state{ Wt::cpp17::any_cast<std::shared_ptr<State>>(continuation.data()) };

            // Aliasing: hands out the answer while the state that owns it stays alive.
            return std::shared_ptr<const ProxyAnswer>{ state, &state->answer() };
        }

        template<typename Params>
        void fillCallbacks(Params& params, const std::shared_ptr<State>& state)
        {
            // The caller decides what a non-200 means, so every status it gets is its own.
            params.treatAnyStatusAsSuccess = true;

            params.onSuccessFunc = [state](const Wt::Http::Message& msg) {
                std::string contentType;
                if (const std::string* header{ msg.getHeader("Content-Type") })
                    contentType = *header;

                state->settle(msg.status(), std::move(contentType), msg.body());
            };

            params.onFailureFunc = [state]() {
                state->settle(502, {}, {}); // Bad Gateway
            };
        }

        template<typename Params, typename SendFunc>
        std::shared_ptr<const ProxyAnswer> proxy(const Wt::Http::Request& request, Wt::Http::Response& response,
                                                 boost::asio::io_context& ioContext, Params&& params, std::chrono::seconds deadline, SendFunc&& send)
        {
            if (Wt::Http::ResponseContinuation * continuation{ request.continuation() })
                return takeAnswer(*continuation);

            // Nothing has been written to the response yet, so its status and mime type are still
            // free to be set on the way back in.
            Wt::Http::ResponseContinuation* continuation{ response.createContinuation() };

            // Wt already owns the continuation through a shared_ptr (WResource::addContinuation),
            // so this observes that ownership rather than starting a second one.
            auto state{ std::make_shared<State>(continuation->weak_from_this(), ioContext) };
            continuation->setData(state);
            continuation->waitForMoreData();

            // Whichever gets there first -- the answer, a delivery failure, or the deadline --
            // settles the request; the others find it settled and do nothing.
            fillCallbacks(params, state);

            // The send queue retries and backs off, so an answer is bounded but not promptly
            // bounded. Without this, one request MuMa never answers holds a connection open for
            // minutes.
            state->armDeadline(deadline);

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
