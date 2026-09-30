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

#include <filesystem>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include <gtest/gtest.h>

#include "PriorityFolderQueue.hpp"
#include "ScanContext.hpp"
#include "ScanStepSequence.hpp"
#include "steps/IPriorityScanYield.hpp"
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

        // What happened, in order, across the library scan and the passes inside it.
        using Journal = std::vector<std::string>;

        // Stands in for ScanStepScanFiles in a library-wide scan: walks `fileCount` files and,
        // between two of them, asks whether priority work is due -- the same question the real
        // step asks after handing a batch to the job scheduler. `onFile` lets a test act as the
        // web thread in the middle of the walk.
        class WalkingStep : public IScanStep
        {
        public:
            WalkingStep(Journal& journal, IPriorityScanYield& yield, std::size_t fileCount, std::function<void(std::size_t)> onFile)
                : _journal{ journal }
                , _yield{ yield }
                , _fileCount{ fileCount }
                , _onFile{ std::move(onFile) }
            {
            }

            ScanStep getStep() const override { return ScanStep::ScanFiles; }
            core::LiteralString getStepName() const override { return "walk"; }
            bool needProcess(const ScanContext&) const override { return true; }

            void process(ScanContext& context) override
            {
                ++runCount;
                for (std::size_t file{}; file < _fileCount; ++file)
                {
                    _journal.push_back("file " + std::to_string(file));
                    context.stats.scans += 1;
                    _onFile(file);

                    if (_yield.isPriorityWorkDue())
                        _yield.runPriorityWork();
                }
            }

            std::size_t runCount{};

        private:
            Journal& _journal;
            IPriorityScanYield& _yield;
            const std::size_t _fileCount;
            std::function<void(std::size_t)> _onFile;
        };

        // A step that only notes when it ran and, in a scoped context, which folders it was given.
        class JournalStep : public IScanStep
        {
        public:
            JournalStep(Journal& journal, core::LiteralString name, bool* interruptFlag = nullptr)
                : _journal{ journal }
                , _name{ name }
                , _interruptFlag{ interruptFlag }
            {
            }

            ScanStep getStep() const override { return ScanStep::CheckForRemovedFiles; }
            core::LiteralString getStepName() const override { return _name; }
            bool needProcess(const ScanContext&) const override { return true; }

            void process(ScanContext& context) override
            {
                std::string entry{ _name.str() };
                for (const std::filesystem::path& folder : context.scanOptions.scanDirectories)
                    entry += " " + folder.string();
                _journal.push_back(entry);
                context.stats.additions += context.scanOptions.scanDirectories.size();

                if (_interruptFlag)
                    *_interruptFlag = true;
            }

        private:
            Journal& _journal;
            core::LiteralString _name;
            bool* _interruptFlag{};
        };

        // A step whose write the database refuses, as a lms.db still locked by music-manager
        // after busy_timeout does (bug report 132).
        class ThrowingStep : public IScanStep
        {
        public:
            ScanStep getStep() const override { return ScanStep::ComputeClusterStats; }
            core::LiteralString getStepName() const override { return "throwing"; }
            bool needProcess(const ScanContext&) const override { return true; }
            void process(ScanContext&) override { throw std::runtime_error{ "database is locked" }; }
        };

        // The part of ScannerService that answers the steps' question, with a hand-driven clock.
        class TestYield : public IPriorityScanYield
        {
        public:
            TestYield(PriorityFolderQueue& queue, std::vector<std::unique_ptr<IScanStep>>& passSteps, const bool& interrupted)
                : _queue{ queue }
                , _passSteps{ passSteps }
                , _interrupted{ interrupted }
            {
            }

            bool isPriorityWorkDue() override { return !_inPass && _queue.isDue(now, PriorityFolderQueue::Moment::DuringLibraryScan); }

            void runPriorityWork() override
            {
                _inPass = true;
                if (const std::optional<ScanContext> pass{ runPriorityPass(_passSteps, _queue, now, _interrupted) })
                {
                    passes.push_back(pass->scanOptions.scanDirectories);
                    _queue.priorityPassFinished(now);
                }
                _inPass = false;
            }

            PriorityFolderQueue::Clock::time_point now{};
            std::vector<std::vector<std::filesystem::path>> passes;

        private:
            PriorityFolderQueue& _queue;
            std::vector<std::unique_ptr<IScanStep>>& _passSteps;
            const bool& _interrupted;
            bool _inPass{};
        };

        constexpr PriorityFolderQueue::Timing priorityTiming{
            .collect = ScanRequestCollector::Timing{ .quietPeriod = std::chrono::seconds{ 5 }, .maxDelay = std::chrono::seconds{ 60 } },
            .minGapDuringLibraryScan = std::chrono::seconds{ 120 },
        };
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

    TEST(ScanStepSequence, betweenStepsRunsAfterEveryCompletedStepButNotAfterTheLast)
    {
        std::vector<IScanStep*> raw;
        auto steps{ makeSteps(raw) };
        ScanContext context;
        bool interrupted{};
        std::size_t calls{};

        EXPECT_EQ(runScanSteps(steps, context, interrupted, ignoreProgress, 0, [&] { ++calls; }), 3);
        EXPECT_EQ(calls, 2);
    }

    // Bug report 126. A library-wide scan used to leave every announced folder waiting until it
    // had walked the whole library -- well over an hour on production. The folder announced in
    // the middle of the walk is now read in a priority pass before the library scan finishes, the
    // walk carries on from where it was instead of starting over (bug report 120's abort loop), and
    // a folder announced twice is read once.
    TEST(ScanStepSequence, aFolderAnnouncedDuringALibraryScanIsReadBeforeItFinishes)
    {
        Journal journal;
        PriorityFolderQueue queue{ priorityTiming };
        bool interrupted{};

        std::vector<std::unique_ptr<IScanStep>> passSteps;
        passSteps.push_back(std::make_unique<JournalStep>(journal, "pass"));

        TestYield yield{ queue, passSteps, interrupted };
        const auto announceDuringTheWalk{ [&](std::size_t file) {
            if (file == 1)
            {
                // The downloader and the tagger both announce the same folder.
                queue.add({ "/music/Soundcloud/2TD" }, yield.now);
                queue.add({ "/music/Soundcloud/2TD", "/music/Youtube/Gearbox Digital" }, yield.now);
            }
            yield.now += std::chrono::seconds{ 3 };
        } };

        std::vector<std::unique_ptr<IScanStep>> librarySteps;
        librarySteps.push_back(std::make_unique<WalkingStep>(journal, yield, 6, announceDuringTheWalk));
        librarySteps.push_back(std::make_unique<JournalStep>(journal, "after walk"));
        auto& walk{ static_cast<WalkingStep&>(*librarySteps.front()) };

        ScanContext libraryContext;
        const std::size_t stoppedAt{ runScanSteps(librarySteps, libraryContext, interrupted, ignoreProgress) };

        EXPECT_EQ(stoppedAt, librarySteps.size()); // completed, never interrupted
        EXPECT_FALSE(interrupted);
        EXPECT_EQ(walk.runCount, 1);                  // the walk did not start over
        EXPECT_EQ(libraryContext.stats.scans, 6);     // every file exactly once
        EXPECT_EQ(libraryContext.stats.additions, 0); // the pass counts in its own context

        ASSERT_EQ(yield.passes.size(), 1);
        EXPECT_EQ(yield.passes.front(), (std::vector<std::filesystem::path>{ "/music/Soundcloud/2TD", "/music/Youtube/Gearbox Digital" }));
        EXPECT_EQ(queue.pendingCount(), 0);

        // Announced after file 1, due after the five-second quiet period, read mid-walk.
        const Journal expected{ "file 0", "file 1", "file 2", "pass /music/Soundcloud/2TD /music/Youtube/Gearbox Digital", "file 3", "file 4", "file 5", "after walk" };
        EXPECT_EQ(journal, expected);
    }

    // Between steps is the other place a library scan makes room: after the walk, a folder does
    // not wait for the remaining steps either.
    TEST(ScanStepSequence, aFolderAnnouncedDuringTheWalkButDueAfterItIsReadBetweenSteps)
    {
        Journal journal;
        PriorityFolderQueue queue{ priorityTiming };
        bool interrupted{};

        std::vector<std::unique_ptr<IScanStep>> passSteps;
        passSteps.push_back(std::make_unique<JournalStep>(journal, "pass"));
        TestYield yield{ queue, passSteps, interrupted };

        std::vector<std::unique_ptr<IScanStep>> librarySteps;
        librarySteps.push_back(std::make_unique<WalkingStep>(journal, yield, 2, [&](std::size_t file) {
            if (file == 1)
                queue.add({ "/music/EPs/__TODO/SB4U017" }, yield.now);
        }));
        librarySteps.push_back(std::make_unique<JournalStep>(journal, "remove"));
        librarySteps.push_back(std::make_unique<JournalStep>(journal, "associate"));

        ScanContext libraryContext;
        const auto betweenSteps{ [&] {
            yield.now += std::chrono::seconds{ 10 };
            if (yield.isPriorityWorkDue())
                yield.runPriorityWork();
        } };

        EXPECT_EQ(runScanSteps(librarySteps, libraryContext, interrupted, ignoreProgress, 0, betweenSteps), 3);
        const Journal expected{ "file 0", "file 1", "pass /music/EPs/__TODO/SB4U017", "remove", "associate" };
        EXPECT_EQ(journal, expected);
    }

    // An admin abort or a shutdown during a pass must not lose the announced folders.
    TEST(ScanStepSequence, aPriorityPassCutShortPutsItsFoldersBack)
    {
        Journal journal;
        PriorityFolderQueue queue{ priorityTiming };
        bool interrupted{};

        std::vector<std::unique_ptr<IScanStep>> passSteps;
        passSteps.push_back(std::make_unique<JournalStep>(journal, "pass", &interrupted));
        passSteps.push_back(std::make_unique<JournalStep>(journal, "never"));

        queue.add({ "/music/A" }, PriorityFolderQueue::Clock::time_point{});
        const std::optional<ScanContext> pass{ runPriorityPass(passSteps, queue, PriorityFolderQueue::Clock::time_point{} + std::chrono::seconds{ 10 }, interrupted) };

        ASSERT_TRUE(pass.has_value());
        EXPECT_EQ(journal, Journal{ "pass /music/A" });
        EXPECT_EQ(queue.pendingCount(), 1);
    }

    // A step that throws ends the pass too; the folders it took must not go down with it.
    TEST(ScanStepSequence, aPriorityPassEndedByAnExceptionPutsItsFoldersBack)
    {
        Journal journal;
        PriorityFolderQueue queue{ priorityTiming };
        bool interrupted{};

        std::vector<std::unique_ptr<IScanStep>> passSteps;
        passSteps.push_back(std::make_unique<JournalStep>(journal, "pass"));
        passSteps.push_back(std::make_unique<ThrowingStep>());
        passSteps.push_back(std::make_unique<JournalStep>(journal, "never"));

        queue.add({ "/music/A" }, PriorityFolderQueue::Clock::time_point{});
        EXPECT_THROW(static_cast<void>(runPriorityPass(passSteps, queue, PriorityFolderQueue::Clock::time_point{} + std::chrono::seconds{ 10 }, interrupted)), std::runtime_error);

        EXPECT_EQ(journal, Journal{ "pass /music/A" });
        EXPECT_EQ(queue.pendingCount(), 1);
    }

    TEST(ScanStepSequence, noPriorityPassWhenNothingIsDue)
    {
        Journal journal;
        PriorityFolderQueue queue{ priorityTiming };
        bool interrupted{};
        std::vector<std::unique_ptr<IScanStep>> passSteps;
        passSteps.push_back(std::make_unique<JournalStep>(journal, "pass"));

        const PriorityFolderQueue::Clock::time_point start{};
        queue.add({ "/music/A" }, start);

        EXPECT_FALSE(runPriorityPass(passSteps, queue, start + std::chrono::seconds{ 2 }, interrupted).has_value());
        EXPECT_TRUE(journal.empty());
        EXPECT_EQ(queue.pendingCount(), 1);
    }
    // Bug report 136: a tagger round that announced a hundred folders does not turn one pass into
    // a small library scan; the pass reads its share and leaves the rest queued.
    TEST(ScanStepSequence, aPriorityPassReadsAtMostItsShareOfFolders)
    {
        Journal journal;
        PriorityFolderQueue queue{ priorityTiming };
        bool interrupted{};
        std::vector<std::unique_ptr<IScanStep>> passSteps;
        passSteps.push_back(std::make_unique<JournalStep>(journal, "pass"));

        const PriorityFolderQueue::Clock::time_point start{};
        std::vector<std::filesystem::path> folders;
        for (std::size_t i{}; i < maxFoldersPerPriorityPass + 7; ++i)
            folders.emplace_back("/music/EPs/Label/CAT" + std::to_string(1000 + i));
        queue.add(folders, start);

        const std::optional<ScanContext> pass{ runPriorityPass(passSteps, queue, start + std::chrono::seconds{ 10 }, interrupted) };

        ASSERT_TRUE(pass.has_value());
        EXPECT_EQ(pass->scanOptions.scanDirectories.size(), maxFoldersPerPriorityPass);
        EXPECT_EQ(queue.pendingCount(), 7);
    }

} // namespace lms::scanner::tests
