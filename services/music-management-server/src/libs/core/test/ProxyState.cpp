/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <chrono>
#include <memory>

#include <gtest/gtest.h>

#include <boost/asio/io_context.hpp>

#include "http/ProxyState.hpp"

namespace lms::core::http::tests
{
    namespace
    {
        // Stands in for Wt::Http::ResponseContinuation, whose constructor is private. Like Wt's,
        // it is owned elsewhere by a shared_ptr and freed without telling the proxy state.
        // The wake-up count lives outside the object, so a call through a dangling pointer would
        // still show up as a count that moved after the continuation was gone.
        class FakeContinuation
        {
        public:
            explicit FakeContinuation(int& wakes)
                : _wakes{ wakes }
            {
            }

            void haveMoreData() { ++_wakes; }

        private:
            int& _wakes;
        };

        using State = detail::ProxyState<FakeContinuation>;

        constexpr std::chrono::milliseconds shortDeadline{ 10 };
        constexpr std::chrono::hours longDeadline{ 1 };
        constexpr std::chrono::seconds runBudget{ 5 };
    } // namespace

    // The normal path: MuMa answers, Wt re-enters the handler, returns, and frees the
    // continuation. A deadline that lands after that must not reach for it.
    TEST(ProxyState, deadlineAfterNormalCompletionTouchesNothing)
    {
        boost::asio::io_context ioContext;
        int wakes{};
        auto continuation{ std::make_shared<FakeContinuation>(wakes) };
        auto state{ std::make_shared<State>(continuation, ioContext) };
        state->armDeadline(longDeadline);

        EXPECT_TRUE(state->settle(200, "image/jpeg", "bytes"));
        EXPECT_EQ(wakes, 1);

        continuation.reset(); // Wt's second pass is done; WResource drops its reference

        // The deadline firing anyway -- its completion was already queued when the answer
        // cancelled the timer -- is exactly this call.
        EXPECT_FALSE(state->settle(504, {}, {}));
        EXPECT_EQ(wakes, 1);
        EXPECT_EQ(state->answer().status, 200);
        EXPECT_EQ(state->answer().body, "bytes");
    }

    // Normal completion cancels the deadline, so the io_context has no work left: a timer still
    // pending would keep run_for() busy for the whole budget and leave the context running.
    TEST(ProxyState, normalCompletionCancelsTheDeadline)
    {
        boost::asio::io_context ioContext;
        int wakes{};
        auto continuation{ std::make_shared<FakeContinuation>(wakes) };
        auto state{ std::make_shared<State>(continuation, ioContext) };
        state->armDeadline(longDeadline);

        EXPECT_TRUE(state->settle(200, {}, {}));

        const auto start{ std::chrono::steady_clock::now() };
        ioContext.run_for(runBudget);

        EXPECT_TRUE(ioContext.stopped());
        EXPECT_LT(std::chrono::steady_clock::now() - start, runBudget);
        EXPECT_EQ(wakes, 1);
        EXPECT_EQ(state->answer().status, 200);
    }

    // The client hangs up while the request is parked: Wt frees the continuation
    // (ResponseContinuation::handleDisconnect) with nothing settled. The deadline then fires for
    // real and must record the timeout without waking anybody.
    TEST(ProxyState, deadlineAfterClientDisconnectTouchesNothing)
    {
        boost::asio::io_context ioContext;
        int wakes{};
        auto continuation{ std::make_shared<FakeContinuation>(wakes) };
        auto state{ std::make_shared<State>(continuation, ioContext) };
        state->armDeadline(shortDeadline);

        continuation.reset();
        ioContext.run_for(runBudget);

        EXPECT_EQ(wakes, 0);
        EXPECT_EQ(state->answer().status, 504);
    }

    // Same disconnect, but MuMa's answer arrives before the deadline does.
    TEST(ProxyState, answerAfterClientDisconnectTouchesNothing)
    {
        boost::asio::io_context ioContext;
        int wakes{};
        auto continuation{ std::make_shared<FakeContinuation>(wakes) };
        auto state{ std::make_shared<State>(continuation, ioContext) };
        state->armDeadline(longDeadline);

        continuation.reset();

        EXPECT_TRUE(state->settle(200, {}, {}));
        EXPECT_EQ(wakes, 0);

        ioContext.run_for(runBudget);
        EXPECT_TRUE(ioContext.stopped());
    }

    // MuMa never answers: the deadline wakes the continuation once with a 504, and the answer
    // that finally trickles out of the send queue afterwards changes nothing.
    TEST(ProxyState, deadlineWinsOverALateAnswer)
    {
        boost::asio::io_context ioContext;
        int wakes{};
        auto continuation{ std::make_shared<FakeContinuation>(wakes) };
        auto state{ std::make_shared<State>(continuation, ioContext) };
        state->armDeadline(shortDeadline);

        ioContext.run_for(runBudget);

        EXPECT_EQ(wakes, 1);
        EXPECT_EQ(state->answer().status, 504);

        EXPECT_FALSE(state->settle(200, "image/jpeg", "late"));
        EXPECT_EQ(wakes, 1);
        EXPECT_EQ(state->answer().status, 504);
        EXPECT_TRUE(state->answer().body.empty());
    }
} // namespace lms::core::http::tests
