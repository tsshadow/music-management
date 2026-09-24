/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include "http/ClientRequest.hpp"
#include "http/RetryPolicy.hpp"

namespace lms::core::http::tests
{
    namespace
    {
        constexpr std::size_t maxRetryCount{ 2 };
        constexpr std::size_t errorsBeforeThrottling{ 3 };
        constexpr std::size_t maxRateLimitRetries{ 3 };

        using Priority = ClientRequestParameters::Priority;

        // A queued GET whose relative URL names it, so a test can tell which one was shed.
        std::unique_ptr<ClientRequest> makeRequest(Priority priority, std::string name)
        {
            ClientGETRequestParameters params;
            params.priority = priority;
            params.relativeUrl = std::move(name);
            return std::make_unique<ClientRequest>(std::move(params));
        }

        std::size_t countQueued(const SendQueueContents& queue)
        {
            std::size_t count{};
            for (const auto& [priority, requests] : queue)
                count += requests.size();
            return count;
        }
    } // namespace

    // One request failing is not evidence that the endpoint is down, and pausing the whole queue
    // over it is how a single artist image used to hold up scrobbles and ratings for 30 seconds.
    TEST(SendQueueRetryPolicy, oneFailureDoesNotPauseTheQueue)
    {
        const RetryDecision decision{ decideAfterTransportError(0, maxRetryCount, 1, errorsBeforeThrottling) };

        EXPECT_TRUE(decision.retryRequest);
        EXPECT_FALSE(decision.throttleQueue);
    }

    // Failing over and over in a row is evidence, and then backing the whole queue off is right:
    // hammering an endpoint that is down helps nobody.
    TEST(SendQueueRetryPolicy, repeatedFailuresPauseTheQueue)
    {
        const RetryDecision decision{ decideAfterTransportError(0, maxRetryCount, errorsBeforeThrottling, errorsBeforeThrottling) };

        EXPECT_TRUE(decision.throttleQueue);
    }

    TEST(SendQueueRetryPolicy, aRequestIsGivenUpOnceItsRetriesRunOut)
    {
        EXPECT_TRUE(decideAfterTransportError(maxRetryCount - 1, maxRetryCount, 1, errorsBeforeThrottling).retryRequest);
        EXPECT_FALSE(decideAfterTransportError(maxRetryCount, maxRetryCount, 1, errorsBeforeThrottling).retryRequest);
        EXPECT_FALSE(decideAfterTransportError(maxRetryCount + 1, maxRetryCount, 1, errorsBeforeThrottling).retryRequest);
    }

    // The two decisions are independent: giving up on one request says nothing about whether the
    // queue should keep going, and vice versa.
    TEST(SendQueueRetryPolicy, givingUpOnARequestIsSeparateFromPausingTheQueue)
    {
        const RetryDecision exhausted{ decideAfterTransportError(maxRetryCount, maxRetryCount, 1, errorsBeforeThrottling) };
        EXPECT_FALSE(exhausted.retryRequest);
        EXPECT_FALSE(exhausted.throttleQueue);

        const RetryDecision endpointDown{ decideAfterTransportError(0, maxRetryCount, errorsBeforeThrottling + 5, errorsBeforeThrottling) };
        EXPECT_TRUE(endpointDown.retryRequest);
        EXPECT_TRUE(endpointDown.throttleQueue);
    }

    // A proxied request wants MuMa's own answer, 429 included, and must not freeze the queue.
    TEST(SendQueueRetryPolicy, aProxied429IsForwardedToTheCaller)
    {
        EXPECT_EQ(decideAfterRateLimited(true, 0, maxRateLimitRetries), RateLimitedAction::ForwardToCaller);
        EXPECT_EQ(decideAfterRateLimited(true, maxRateLimitRetries + 10, maxRateLimitRetries), RateLimitedAction::ForwardToCaller);
    }

    // A 429 on a regular request is retried, but only a bounded number of times: an endpoint
    // that answers 429 forever used to keep the request -- and the queue -- stuck forever.
    TEST(SendQueueRetryPolicy, a429IsRetriedAFewTimesThenGivenUp)
    {
        for (std::size_t retry{}; retry < maxRateLimitRetries; ++retry)
            EXPECT_EQ(decideAfterRateLimited(false, retry, maxRateLimitRetries), RateLimitedAction::RetryLater) << "retry " << retry;

        EXPECT_EQ(decideAfterRateLimited(false, maxRateLimitRetries, maxRateLimitRetries), RateLimitedAction::GiveUp);
        EXPECT_EQ(decideAfterRateLimited(false, maxRateLimitRetries + 1, maxRateLimitRetries), RateLimitedAction::GiveUp);
    }

    TEST(SendQueueRetryPolicy, aQueueWithRoomShedsNothing)
    {
        SendQueueContents queue;
        queue[Priority::Normal].push_back(makeRequest(Priority::Normal, "a"));

        EXPECT_TRUE(shedOldestIfFull(queue, 2) == nullptr);
        EXPECT_EQ(countQueued(queue), 1);

        SendQueueContents empty;
        EXPECT_TRUE(shedOldestIfFull(empty, 0) == nullptr);
    }

    // A full queue gives up its oldest least-important request, not a fresh or urgent one.
    TEST(SendQueueRetryPolicy, aFullQueueShedsTheOldestLowestPriorityRequest)
    {
        SendQueueContents queue;
        queue[Priority::High].push_back(makeRequest(Priority::High, "high"));
        queue[Priority::Normal].push_back(makeRequest(Priority::Normal, "normal-old"));
        queue[Priority::Normal].push_back(makeRequest(Priority::Normal, "normal-new"));
        queue[Priority::Low]; // present but empty: must be skipped

        const std::unique_ptr<ClientRequest> shed{ shedOldestIfFull(queue, 3) };
        ASSERT_TRUE(shed != nullptr);
        EXPECT_EQ(shed->getParameters().relativeUrl, "normal-old");
        EXPECT_EQ(countQueued(queue), 2);
        EXPECT_EQ(queue[Priority::Normal].front()->getParameters().relativeUrl, "normal-new");

        queue[Priority::Low].push_back(makeRequest(Priority::Low, "low"));
        const std::unique_ptr<ClientRequest> shedLow{ shedOldestIfFull(queue, 3) };
        ASSERT_TRUE(shedLow != nullptr);
        EXPECT_EQ(shedLow->getParameters().relativeUrl, "low");
    }

    // The bound holds however long the outage lasts: queueing through shedOldestIfFull never
    // lets the queue grow past its limit.
    TEST(SendQueueRetryPolicy, theQueueNeverGrowsPastItsBound)
    {
        constexpr std::size_t maxQueued{ 10 };
        SendQueueContents queue;
        std::size_t shedCount{};
        for (std::size_t i{}; i < 100; ++i)
        {
            if (shedOldestIfFull(queue, maxQueued))
                ++shedCount;
            queue[Priority::Normal].push_back(makeRequest(Priority::Normal, std::to_string(i)));
            ASSERT_LE(countQueued(queue), maxQueued);
        }
        EXPECT_EQ(shedCount, 90);
        EXPECT_EQ(queue[Priority::Normal].front()->getParameters().relativeUrl, "90");
    }
} // namespace lms::core::http::tests
