/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <iostream>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

#include "core/ILogger.hpp"

namespace lms::feedback::tests
{
    // The logger test-feedback runs with: keeps every WARNING so a test can check what LMS told
    // the administrator, and prints ERROR and worse as the default test logger did.
    class CapturingLogger final : public core::logging::ILogger
    {
    public:
        // Every WARNING logged so far, oldest first.
        static std::vector<std::string> warnings()
        {
            const std::scoped_lock lock{ mutex() };
            return captured();
        }

        static void clearWarnings()
        {
            const std::scoped_lock lock{ mutex() };
            captured().clear();
        }

    private:
        bool isSeverityActive(core::logging::Severity severity) const override { return severity <= core::logging::Severity::WARNING; }

        void processLog(const core::logging::Log& log) override { processLog(log.getModule(), log.getSeverity(), log.getMessage()); }

        void processLog(core::logging::Module, core::logging::Severity severity, std::string_view message) override
        {
            if (severity != core::logging::Severity::WARNING)
            {
                std::cerr << message << '\n';
                return;
            }
            const std::scoped_lock lock{ mutex() };
            captured().emplace_back(message);
        }

        static std::mutex& mutex()
        {
            static std::mutex instance;
            return instance;
        }

        static std::vector<std::string>& captured()
        {
            static std::vector<std::string> instance;
            return instance;
        }
    };
} // namespace lms::feedback::tests
