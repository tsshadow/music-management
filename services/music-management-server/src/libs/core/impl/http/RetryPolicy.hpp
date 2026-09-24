/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <cstddef>
#include <deque>
#include <map>
#include <memory>

#include "core/http/ClientRequestParameters.hpp"

namespace lms::core::http
{
    struct RetryDecision
    {
        bool retryRequest{};  // put this request back on the queue
        bool throttleQueue{}; // pause the queue as a whole, not just this request
    };

    // A transport error used to pause the whole SendQueue for the retry wait, which meant one
    // failing request -- an artist image MuMa could not answer, say -- stopped scrobbles and
    // ratings dead for the same 30 seconds. Those are two different questions, so they are answered
    // separately here: whether this request deserves another go, and whether the endpoint looks
    // down badly enough to stop sending altogether.
    RetryDecision decideAfterTransportError(std::size_t requestRetryCount, std::size_t maxRetryCount,
                                            std::size_t consecutiveErrorCount, std::size_t consecutiveErrorsBeforeThrottling);

    // What to do with a request the endpoint answered with 429 Too Many Requests.
    enum class RateLimitedAction
    {
        ForwardToCaller, // hand the 429 to the caller as its answer (reverse-proxy requests)
        RetryLater,      // requeue it and pause the queue for the rate-limit window
        GiveUp,          // report failure: it has been rate limited too often already
    };

    // A 429 used to go back to the head of the queue with no limit, so an endpoint that kept
    // answering 429 froze the queue for good, and a proxied call -- whose caller wants the
    // upstream status verbatim -- paused every other request for 30 seconds as well.
    RateLimitedAction decideAfterRateLimited(bool forwardAnyStatus, std::size_t rateLimitRetryCount, std::size_t maxRateLimitRetries);

    class ClientRequest;
    using SendQueueContents = std::map<ClientRequestParameters::Priority, std::deque<std::unique_ptr<ClientRequest>>>;

    // Makes room for one more request when \p queue already holds \p maxQueuedRequests or
    // more: removes and returns the oldest request of the least important non-empty priority,
    // which the caller must then fail. Returns nullptr when there is room. Without a bound, an
    // unreachable endpoint let the queue -- and memory -- grow for as long as the outage lasted.
    std::unique_ptr<ClientRequest> shedOldestIfFull(SendQueueContents& queue, std::size_t maxQueuedRequests);
} // namespace lms::core::http
