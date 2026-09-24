/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "RetryPolicy.hpp"

#include "ClientRequest.hpp"

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

    RateLimitedAction decideAfterRateLimited(bool forwardAnyStatus, std::size_t rateLimitRetryCount, std::size_t maxRateLimitRetries)
    {
        if (forwardAnyStatus)
            return RateLimitedAction::ForwardToCaller;
        if (rateLimitRetryCount < maxRateLimitRetries)
            return RateLimitedAction::RetryLater;
        return RateLimitedAction::GiveUp;
    }

    std::unique_ptr<ClientRequest> shedOldestIfFull(SendQueueContents& queue, std::size_t maxQueuedRequests)
    {
        std::size_t queuedCount{};
        for (const auto& [priority, requests] : queue)
            queuedCount += requests.size();

        if (queuedCount < maxQueuedRequests)
            return nullptr;

        // The map is ordered High, Normal, Low: walk it backwards to find the least important.
        for (auto it{ queue.rbegin() }; it != queue.rend(); ++it)
        {
            if (it->second.empty())
                continue;

            std::unique_ptr<ClientRequest> shed{ std::move(it->second.front()) };
            it->second.pop_front();
            return shed;
        }

        return nullptr;
    }
} // namespace lms::core::http
