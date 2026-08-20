/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <cstddef>

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
} // namespace lms::core::http
