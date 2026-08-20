/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include "http/RetryPolicy.hpp"

namespace lms::core::http::tests
{
    namespace
    {
        constexpr std::size_t maxRetryCount{ 2 };
        constexpr std::size_t errorsBeforeThrottling{ 3 };
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
} // namespace lms::core::http::tests
