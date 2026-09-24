/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <utility>

#include <boost/asio/io_context.hpp>
#include <boost/asio/steady_timer.hpp>

#include "core/http/ProxyContinuation.hpp"

namespace lms::core::http::detail
{
    // Carries one proxied request across the two passes of its continuation, and decides which of
    // the three possible endings -- the answer, a delivery failure, the deadline -- gets to wake it.
    //
    // It holds the continuation by weak_ptr, never by raw pointer. Wt owns a continuation through
    // the WResource that created it (WResource::addContinuation keeps the only lasting shared_ptr)
    // and frees it the moment that list lets go: after the handler's second pass returns, or when
    // the client disconnects while it is parked (ResponseContinuation::handleDisconnect calls
    // WResource::removeContinuation). Neither event tells this object, and both the send queue's
    // callback and the deadline timer can outlive it -- so a raw pointer here was a use-after-free
    // waiting for a client to hang up on a slow MuMa. See docs/bug-reports/066.
    //
    // Templated on the continuation type only so a test can stand in for Wt's, whose constructor
    // is private. Production uses Wt::Http::ResponseContinuation.
    template<typename Continuation>
    class ProxyState : public std::enable_shared_from_this<ProxyState<Continuation>>
    {
    public:
        ProxyState(std::weak_ptr<Continuation> continuation, boost::asio::io_context& ioContext)
            : _continuation{ std::move(continuation) }
            , _deadline{ ioContext }
        {
        }

        // Starts the deadline. The timer's handler keeps this state alive until it has run or been
        // cancelled, so it must not be armed before the object is owned by a shared_ptr.
        void armDeadline(std::chrono::steady_clock::duration deadline)
        {
            _deadline.expires_after(deadline);
            _deadline.async_wait([self = this->shared_from_this()](const boost::system::error_code& ec) {
                if (ec == boost::asio::error::operation_aborted)
                    return;

                self->settle(504, {}, {}); // Gateway Timeout
            });
        }

        // Records the ending and wakes the continuation, if nothing got there first. Returns
        // whether this call was the one that settled it. Safe to call after Wt has freed the
        // continuation: the wake-up is then simply skipped, since there is nobody left to answer.
        bool settle(int status, std::string contentType, std::string body)
        {
            if (_settled.exchange(true))
                return false;

            _answer.status = status;
            _answer.contentType = std::move(contentType);
            _answer.body = std::move(body);

            // Normal completion: the deadline has nothing left to guard.
            boost::system::error_code ignored;
            _deadline.cancel(ignored);

            // Locking holds the continuation alive for the length of the call, so Wt cannot free
            // it between the check and the use. A continuation Wt already cancelled but that is
            // still alive is harmless too: haveMoreData() finds its resource cleared and returns.
            if (const std::shared_ptr<Continuation> continuation{ _continuation.lock() })
                continuation->haveMoreData();

            return true;
        }

        const ProxyAnswer& answer() const { return _answer; }

    private:
        std::atomic<bool> _settled{};
        ProxyAnswer _answer;
        std::weak_ptr<Continuation> _continuation;
        boost::asio::steady_timer _deadline;
    };
} // namespace lms::core::http::detail
