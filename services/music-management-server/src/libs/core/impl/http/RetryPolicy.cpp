/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "RetryPolicy.hpp"

namespace lms::core::http
{
    RetryDecision decideAfterTransportError(std::size_t requestRetryCount, std::size_t maxRetryCount,
                                            std::size_t consecutiveErrorCount, std::size_t consecutiveErrorsBeforeThrottling)
    {
        return RetryDecision{
            .retryRequest = requestRetryCount < maxRetryCount,
            .throttleQueue = consecutiveErrorCount >= consecutiveErrorsBeforeThrottling,
        };
    }
} // namespace lms::core::http
