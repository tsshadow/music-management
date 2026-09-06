/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 *
 * LMS is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * LMS is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with LMS.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <memory>
#include <vector>

#include <gtest/gtest.h>

#include "ScanContext.hpp"
#include "ScanStepSequence.hpp"
#include "steps/IScanStep.hpp"

namespace lms::scanner::tests
{
    namespace
    {
        // A step that records that it ran, can refuse to run, and can raise the interrupt
        // flag from inside process() -- which is exactly what a real step does on a batch
        // boundary when it sees _abortScan.
        class FakeStep : public IScanStep
        {
        public:
            FakeStep(core::LiteralString name, bool* interruptFlag = nullptr)
                : _name{ name }
                , _interruptFlag{ interruptFlag }
            {
            }

            ScanStep getStep() const override { return ScanStep::ScanFiles; }
            core::LiteralString getStepName() const override { return _name; }
            bool needProcess(const ScanContext&) const override { return _needProcess; }

            void process(ScanContext& context) override
            {
                ++runCount;
                context.stats.scans += 1;
                if (_interruptFlag)
                    *_interruptFlag = true;
            }

            void setNeedProcess(bool value) { _needProcess = value; }
            void stopInterrupting() { _interruptFlag = nullptr; }

            std::size_t runCount{};

        private:
            core::LiteralString _name;
            bool* _interruptFlag{};
            bool _needProcess{ true };
        };

        std::vector<std::unique_ptr<IScanStep>> makeSteps(std::vector<IScanStep*>& out, bool* interruptOnSecond = nullptr)
        {
            std::vector<std::unique_ptr<IScanStep>> steps;
            steps.push_back(std::make_unique<FakeStep>("first"));
            steps.push_back(std::make_unique<FakeStep>("second", interruptOnSecond));
            steps.push_back(std::make_unique<FakeStep>("third"));
            for (auto& step : steps)
                out.push_back(step.get());
            return steps;
        }

        void ignoreProgress(const ScanStepStats&)
        {
        }
    } // namespace

    TEST(ScanStepSequence, runsEveryStepAndReportsCompletion)
    {
        std::vector<IScanStep*> raw;
        auto steps{ makeSteps(raw) };
        ScanContext context;
        bool interrupted{};

        const std::size_t stoppedAt{ runScanSteps(steps, context, interrupted, ignoreProgress) };

        EXPECT_EQ(stoppedAt, 3);
        for (IScanStep* step : raw)
            EXPECT_EQ(static_cast<FakeStep*>(step)->runCount, 1);
    }

    TEST(ScanStepSequence, skipsAStepThatDoesNotNeedProcessing)
    {
        std::vector<IScanStep*> raw;
        auto steps{ makeSteps(raw) };
        static_cast<FakeStep*>(raw[1])->setNeedProcess(false);
        ScanContext context;
        bool interrupted{};

        EXPECT_EQ(runScanSteps(steps, context, interrupted, ignoreProgress), 3);
        EXPECT_EQ(static_cast<FakeStep*>(raw[1])->runCount, 0);
        EXPECT_EQ(static_cast<FakeStep*>(raw[2])->runCount, 1);
    }

    TEST(ScanStepSequence, stopsAtTheInterruptedStepAndNamesIt)
    {
        std::vector<IScanStep*> raw;
        bool interrupted{};
        auto steps{ makeSteps(raw, &interrupted) };
        ScanContext context;

        // The second step raises the flag while running, the way a real step does when it
        // sees the abort bool on a batch boundary.
        const std::size_t stoppedAt{ runScanSteps(steps, context, interrupted, ignoreProgress) };

        EXPECT_EQ(stoppedAt, 1);
        EXPECT_EQ(static_cast<FakeStep*>(raw[2])->runCount, 0);
    }

    TEST(ScanStepSequence, resumingRerunsTheInterruptedStepAndKeepsEarlierStats)
    {
        std::vector<IScanStep*> raw;
        bool interrupted{};
        auto steps{ makeSteps(raw, &interrupted) };
        ScanContext context;

        const std::size_t stoppedAt{ runScanSteps(steps, context, interrupted, ignoreProgress) };
        ASSERT_EQ(stoppedAt, 1);
        const std::size_t statsAfterPause{ context.stats.scans };

        // Resume: the flag is down again and the same context comes back in.
        interrupted = false;
        auto& second{ *static_cast<FakeStep*>(raw[1]) };
        second.stopInterrupting();
        second.runCount = 0;

        EXPECT_EQ(runScanSteps(steps, context, interrupted, ignoreProgress, stoppedAt), 3);
        EXPECT_EQ(static_cast<FakeStep*>(raw[0])->runCount, 1); // not run a second time
        EXPECT_EQ(second.runCount, 1);                          // the interrupted step ran again
        EXPECT_GT(context.stats.scans, statsAfterPause);        // earlier work is still counted
    }
} // namespace lms::scanner::tests
