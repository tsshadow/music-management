/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include <gtest/gtest.h>

#include "core/ILogger.hpp"
#include "core/Service.hpp"

// Runs the relay tests with a logger that prints errors only, as test-scrobbling does.
int main(int argc, char** argv)
{
    using namespace lms;
    core::Service<core::logging::ILogger> logger{ core::logging::createLogger(core::logging::Severity::ERROR) };

    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
