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

#include <atomic>
#include <filesystem>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <unistd.h>

#include <gtest/gtest.h>

#include "core/IConfig.hpp"
#include "core/IJobScheduler.hpp"
#include "core/Service.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artwork.hpp"
#include "database/objects/Directory.hpp"
#include "database/objects/Image.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"

#include "FileScanners.hpp"
#include "ScanContext.hpp"
#include "ScannerSettings.hpp"
#include "scanners/IFileScanner.hpp"
#include "steps/ReleaseArtworkRules.hpp"
#include "steps/ScanStepAssociateReleaseImages.hpp"

// Bug report 144: scene releases name their cover `00-artist_-_title-(cat)-web-2026.jpg`, which
// none of the preferred cover names matches. The stems below are real ones from the library.
// Names here are deliberately distinct from the helpers of the other test files: the release
// image builds with CMAKE_UNITY_BUILD, which merges the anonymous namespaces into one unit.
namespace lms::scanner::tests
{
    namespace
    {
        // Answers the string lists a test sets and falls back to the default for the rest, the
        // way a config file without those keys would.
        class ReleaseImageTestConfig final : public core::IConfig
        {
        public:
            std::map<std::string, std::vector<std::string>, std::less<>> strings;
            std::optional<bool> singleImageFallback;

        private:
            std::string_view getString(std::string_view, std::string_view def) override { return def; }
            void visitStrings(std::string_view setting, std::function<void(std::string_view)> func, std::initializer_list<std::string_view> defs) override
            {
                if (const auto it{ strings.find(setting) }; it != strings.end())
                {
                    for (const std::string& value : it->second)
                        func(value);
                    return;
                }
                for (std::string_view def : defs)
                    func(def);
            }
            std::filesystem::path getPath(std::string_view, const std::filesystem::path& def) override { return def; }
            unsigned long getULong(std::string_view, unsigned long def) override { return def; }
            long getLong(std::string_view, long def) override { return def; }
            bool getBool(std::string_view setting, bool def) override
            {
                if (setting == "cover-single-image-fallback" && singleImageFallback)
                    return *singleImageFallback;
                return def;
            }
        };

        ReleaseArtworkRules defaultReleaseImageRules()
        {
            core::Service<core::IConfig> config{ std::make_unique<ReleaseImageTestConfig>() };
            return readReleaseArtworkRules();
        }

        // The stem the fallback picks out of `stems`, or "" for none.
        std::string pickedReleaseImageStem(const std::vector<std::string>& stems)
        {
            const std::optional<std::size_t> picked{ pickFallbackReleaseImage(defaultReleaseImageRules(), stems) };
            return picked ? stems.at(*picked) : std::string{};
        }

        std::filesystem::path makeReleaseImageTestDbPath()
        {
            static std::atomic<unsigned> counter{};
            return std::filesystem::temp_directory_path() / ("lms-test-release-images-" + std::to_string(::getpid()) + "-" + std::to_string(counter++) + ".db");
        }

        class AssociateReleaseImagesTest : public ::testing::Test
        {
        protected:
            AssociateReleaseImagesTest()
                : _dbPath{ makeReleaseImageTestDbPath() }
                , _db{ db::createDb(_dbPath) }
                , _session{ _db->getTLSSession() }
                , _jobScheduler{ core::createJobScheduler("test-release-images", 1) }
            {
                _session.prepareTablesIfNeeded();
                _session.createIndexesIfNeeded();
            }

            ~AssociateReleaseImagesTest() override
            {
                _jobScheduler.reset();
                _db.reset();
                std::error_code ec;
                std::filesystem::remove(_dbPath, ec);
                std::filesystem::remove(_dbPath.string() + "-wal", ec);
                std::filesystem::remove(_dbPath.string() + "-shm", ec);
            }

            AssociateReleaseImagesTest(const AssociateReleaseImagesTest&) = delete;
            AssociateReleaseImagesTest& operator=(const AssociateReleaseImagesTest&) = delete;

            // A release with one track in `directory`.
            db::ReleaseId addRelease(const std::filesystem::path& directory)
            {
                auto transaction{ _session.createWriteTransaction() };
                const db::Release::pointer release{ _session.create<db::Release>(directory.filename().string()) };
                db::Track::pointer track{ _session.create<db::Track>() };
                track.modify()->setAbsoluteFilePath(directory / "01-track.mp3");
                track.modify()->setRelease(release);
                track.modify()->setDirectory(getOrCreateDirectory(directory));
                return release->getId();
            }

            db::ArtworkId addImage(const std::filesystem::path& path)
            {
                auto transaction{ _session.createWriteTransaction() };
                db::Image::pointer image{ _session.create<db::Image>(path) };
                image.modify()->setDirectory(getOrCreateDirectory(path.parent_path()));
                return _session.create<db::Artwork>(image)->getId();
            }

            db::ArtworkId releaseArtwork(db::ReleaseId releaseId)
            {
                auto transaction{ _session.createReadTransaction() };
                return db::Release::find(_session, releaseId)->getPreferredArtworkId();
            }

            // A scan's settings: the current rules as `config` gives them, and the ones the last
            // scan recorded (none: no scan recorded any).
            struct StepSettings
            {
                ScannerSettings current;
                std::optional<ScannerSettings> last;
            };

            // One run of the step, the way a scan with `context` would run it. False when the
            // step said it had nothing to do.
            bool runStep(ScanContext& context, const ReleaseImageTestConfig& configValues = {}, const StepSettings& settings = {})
            {
                core::Service<core::IConfig> config{ std::make_unique<ReleaseImageTestConfig>(configValues) };

                bool abortScan{};
                FileScanners fileScanners;
                const std::filesystem::path cachePath{ "/tmp" };
                ScanStepBase::InitParams params{
                    .jobScheduler = *_jobScheduler,
                    .settings = settings.current,
                    .lastScanSettings = settings.last ? &*settings.last : nullptr,
                    .progressCallback = [](const ScanStepStats&) {},
                    .abortScan = abortScan,
                    .db = *_db,
                    .fileScanners = fileScanners,
                    .cachePath = cachePath,
                };
                ScanStepAssociateReleaseImages concreteStep{ params };
                IScanStep& step{ concreteStep };

                if (!step.needProcess(context))
                    return false;
                step.process(context);
                return true;
            }

            // A library-wide scan that read a changed file.
            void runStepWithChanges(const ReleaseImageTestConfig& configValues = {})
            {
                ScanContext context;
                context.stats.updates = 1;
                ASSERT_TRUE(runStep(context, configValues));
            }

        private:
            db::Directory::pointer getOrCreateDirectory(const std::filesystem::path& path)
            {
                db::Directory::pointer directory{ db::Directory::find(_session, path) };
                if (!directory)
                    directory = _session.create<db::Directory>(path);
                return directory;
            }

            const std::filesystem::path _dbPath;
            std::unique_ptr<db::IDb> _db;
            db::Session& _session;
            std::unique_ptr<core::IJobScheduler> _jobScheduler;
        };
    } // namespace

    TEST(ReleaseArtworkFallback, aSceneCoverIsPicked)
    {
        EXPECT_EQ(pickedReleaseImageStem({ "00-a-rize_-_hold_me_close-(ety014)-single-web-2022" }), "00-a-rize_-_hold_me_close-(ety014)-single-web-2022");
        EXPECT_EQ(pickedReleaseImageStem({ "00_the_purge_-_switch-(spoon137)-web-2018" }), "00_the_purge_-_switch-(spoon137)-web-2018");
        EXPECT_EQ(pickedReleaseImageStem({ "000-va-masters_of_hardcore-2cd-2023-cover", "R-918954-1175427116" }), "000-va-masters_of_hardcore-2cd-2023-cover");
    }

    TEST(ReleaseArtworkFallback, aWordOfTheTitleDoesNotCount)
    {
        // "back" and "inside" are excluded words, but here they belong to the title.
        EXPECT_EQ(pickedReleaseImageStem({ "00-proto_bytez_-_come_back-(ssl171)-single-web-2020-srg" }), "00-proto_bytez_-_come_back-(ssl171)-single-web-2020-srg");
        EXPECT_EQ(pickedReleaseImageStem({ "00_shafar_-_voices_inside-(pm_040)-web-2022" }), "00_shafar_-_voices_inside-(pm_040)-web-2022");
    }

    TEST(ReleaseArtworkFallback, aProofIsNotPicked)
    {
        EXPECT_EQ(pickedReleaseImageStem({ "00-ophidian_-_call_of_the_void-(tdmcd202101)-cd-2021-srg-proof" }), "");
        EXPECT_EQ(pickedReleaseImageStem({ "000-evil_activities-evilution-2cd-2008-(proof)-homely" }), "");
        EXPECT_EQ(pickedReleaseImageStem({ "00_neilio_-_nothing-(dwx322s)-web-2016", "00_neilio_-_nothing-(dwx322s)-web-2016-proof" }), "00_neilio_-_nothing-(dwx322s)-web-2016");
        // "proof" and "proper" share their first letters; whole words tell them apart.
        EXPECT_EQ(pickedReleaseImageStem({ "00-judax-dot.core-(offrage117)-proof-web-2021-ind", "00-judax-dot.core-(offrage117)-proper-web-2021-ind" }), "00-judax-dot.core-(offrage117)-proper-web-2021-ind");
    }

    TEST(ReleaseArtworkFallback, theFrontCoverWinsOverBackProofAndDiscScans)
    {
        const std::vector<std::string> defqon{
            "00-va-defqon.1_power_of_the_tribe_album_mix-(dq008)-cd-flac-2024-back",
            "00-va-defqon.1_power_of_the_tribe_album_mix-(dq008)-cd-flac-2024-front",
            "00-va-defqon.1_power_of_the_tribe_album_mix-(dq008)-cd-flac-2024-proof",
        };
        EXPECT_EQ(pickedReleaseImageStem(defqon), defqon[1]);

        const std::vector<std::string> pengo{
            "00_party_animals_-_aquarius-(db17522)-cds-1996-cover_back-bc",
            "00_party_animals_-_aquarius-(db17522)-cds-1996-cover_disc-bc",
            "00_party_animals_-_aquarius-(db17522)-cds-1996-cover_front-bc",
        };
        EXPECT_EQ(pickedReleaseImageStem(pengo), pengo[2]);

        const std::vector<std::string> darkside{
            "00_va_-_darkside_of_hardcore_event_03-cd-2004-back-sq",
            "00_va_-_darkside_of_hardcore_event_03-cd-2004-cd-sq",
            "00_va_-_darkside_of_hardcore_event_03-cd-2004-inlay-sq",
            "00_va_-_darkside_of_hardcore_event_03-cd-2004-inside-sq",
            "00_va_-_darkside_of_hardcore_event_03-cd-2004-front-sq",
        };
        EXPECT_EQ(pickedReleaseImageStem(darkside), darkside[4]);

        // A cover beats a scan of the disc and a photo of the whole package.
        const std::vector<std::string> bongRa{
            "00-bong-ra-monolith-(prspctrvltcd001)-cd-2012-def",
            "00-bong-ra-monolith-(prspctrvltcd001)-cd-cd_scan-2012-def",
            "00-bong-ra-monolith-(prspctrvltcd001)-cd-proof-2012-def",
        };
        EXPECT_EQ(pickedReleaseImageStem(bongRa), bongRa[0]);

        // Front words in order: "front" before "cover".
        const std::vector<std::string> sirio{
            "00-sirio_-_hc_underground-(nrtx51)-web-2013-cover-sob",
            "00-sirio_-_hc_underground-(nrtx51)-web-2013-folder-sob",
            "00-sirio_-_hc_underground-(nrtx51)-web-2013-front-sob",
        };
        EXPECT_EQ(pickedReleaseImageStem(sirio), sirio[2]);
    }

    TEST(ReleaseArtworkFallback, onlyBackProofAndDiscScansGiveNothing)
    {
        EXPECT_EQ(pickedReleaseImageStem({ "00_rude_awakening-fragments_of_the_future-(t3rdm0144)-cd-2008-back", "00_rude_awakening-fragments_of_the_future-(t3rdm0144)-cd-2008-cd" }), "");
        EXPECT_EQ(pickedReleaseImageStem({ "00-radium_-_livextrax_ep-(pkgrx_05)-vinyl-2004-proof1-zzzz", "00-radium_-_livextrax_ep-(pkgrx_05)-vinyl-2004-proof2-zzzz" }), "");
    }

    TEST(ReleaseArtworkFallback, theOnlyImageOfADirectoryIsPicked)
    {
        EXPECT_EQ(pickedReleaseImageStem({ "R-918954-1175427116" }), "R-918954-1175427116");
        // Unless it says it is something else than a front cover.
        EXPECT_EQ(pickedReleaseImageStem({ "Back" }), "");
        EXPECT_EQ(pickedReleaseImageStem({ "disc" }), "");
        // Two images, neither a scene cover: no guess.
        EXPECT_EQ(pickedReleaseImageStem({ "Crypton", "Crypton - Videos" }), "");
        EXPECT_EQ(pickedReleaseImageStem({}), "");
    }

    TEST(ReleaseArtworkFallback, theRulesAreConfigurable)
    {
        const std::string defaultFingerprint{ computeReleaseArtworkRulesFingerprint(defaultReleaseImageRules()) };
        EXPECT_EQ(computeReleaseArtworkRulesFingerprint(defaultReleaseImageRules()), defaultFingerprint);

        ReleaseImageTestConfig configValues;
        configValues.strings["cover-fallback-file-stem-prefixes"] = {};
        configValues.singleImageFallback = false;
        core::Service<core::IConfig> config{ std::make_unique<ReleaseImageTestConfig>(configValues) };
        const ReleaseArtworkRules rules{ readReleaseArtworkRules() };

        // No prefix: the stem rule is off; and with it off, the lone image is not taken either.
        const std::vector<std::string> sceneCover{ "00_the_purge_-_switch-(spoon137)-web-2018" };
        EXPECT_FALSE(pickFallbackReleaseImage(rules, sceneCover));
        // A different configuration is a different fingerprint: the next scan applies it.
        EXPECT_NE(computeReleaseArtworkRulesFingerprint(rules), defaultFingerprint);
    }

    TEST_F(AssociateReleaseImagesTest, aSceneCoverBecomesTheReleaseArtwork)
    {
        const std::filesystem::path directory{ "/music/EPs/Dirty Workz/DWX818 - Refuzion_ft._Rainage_-_Summer_In_Your_Eyes" };
        const db::ReleaseId release{ addRelease(directory) };
        const db::ArtworkId cover{ addImage(directory / "00-refuzion_ft._rainage_-_summer_in_your_eyes-(dwx818)-single-web-2020-srg.jpg") };

        runStepWithChanges();

        EXPECT_EQ(releaseArtwork(release), cover);
    }

    TEST_F(AssociateReleaseImagesTest, aProofIsNotTheReleaseArtwork)
    {
        const std::filesystem::path withFront{ "/music/Albums/DQ008 - Defqon.1 Power Of The Tribe" };
        const db::ReleaseId frontRelease{ addRelease(withFront) };
        addImage(withFront / "00-va-defqon.1_power_of_the_tribe-(dq008)-cd-2024-back.jpg");
        const db::ArtworkId front{ addImage(withFront / "00-va-defqon.1_power_of_the_tribe-(dq008)-cd-2024-front.jpg") };
        addImage(withFront / "00-va-defqon.1_power_of_the_tribe-(dq008)-cd-2024-proof.jpg");

        const std::filesystem::path proofOnly{ "/music/Albums/EOLCD201601 - Warface - Live For This" };
        const db::ReleaseId proofRelease{ addRelease(proofOnly) };
        addImage(proofOnly / "00-warface_-_live_for_this-(eolcd201601)-cd-2016-srg-proof.jpg");

        runStepWithChanges();

        EXPECT_EQ(releaseArtwork(frontRelease), front);
        EXPECT_FALSE(releaseArtwork(proofRelease).isValid());
    }

    TEST_F(AssociateReleaseImagesTest, theOnlyImageInTheDirectoryIsTheReleaseArtwork)
    {
        const std::filesystem::path directory{ "/music/Vinyl/DB 1756 - Back 2 Bass - I Wanna Be With You" };
        const db::ReleaseId release{ addRelease(directory) };
        const db::ArtworkId only{ addImage(directory / "R-918954-1175427116.jpg") };

        runStepWithChanges();
        EXPECT_EQ(releaseArtwork(release), only);

        // And it is a fallback that can be turned off.
        ReleaseImageTestConfig withoutSingleImage;
        withoutSingleImage.singleImageFallback = false;
        runStepWithChanges(withoutSingleImage);
        EXPECT_FALSE(releaseArtwork(release).isValid());
    }

    TEST_F(AssociateReleaseImagesTest, aPreferredNameStillWins)
    {
        const std::filesystem::path directory{ "/music/EPs/Spoontech/SPOON137 - The_Purge_-_Switch" };
        const db::ReleaseId release{ addRelease(directory) };
        addImage(directory / "00_the_purge_-_switch-(spoon137)-web-2018.jpg");
        const db::ArtworkId folder{ addImage(directory / "folder.jpg") };

        runStepWithChanges();

        EXPECT_EQ(releaseArtwork(release), folder);
    }

    TEST_F(AssociateReleaseImagesTest, newRulesReachEveryReleaseOnTheNextLibraryWideScan)
    {
        const std::filesystem::path directory{ "/music/EPs/Spoontech/SPOON137 - The_Purge_-_Switch" };
        const db::ReleaseId release{ addRelease(directory) };
        const db::ArtworkId cover{ addImage(directory / "00_the_purge_-_switch-(spoon137)-web-2018.jpg") };

        // The last scan applied older rules (an existing database: none recorded).
        StepSettings settings;
        settings.current.releaseArtworkRules = computeReleaseArtworkRulesFingerprint(defaultReleaseImageRules());
        settings.last.emplace();

        // A scoped scan that changed nothing leaves it to the library-wide one...
        ScanContext scoped;
        scoped.scanOptions.scanDirectories = { "/music/EPs/Other" };
        EXPECT_FALSE(runStep(scoped, {}, settings));
        EXPECT_FALSE(releaseArtwork(release).isValid());

        // ...which does it even though no file changed.
        ScanContext libraryWide;
        EXPECT_TRUE(runStep(libraryWide, {}, settings));
        EXPECT_EQ(releaseArtwork(release), cover);

        // Once recorded, an unchanged library-wide scan has nothing to do again.
        settings.last->releaseArtworkRules = settings.current.releaseArtworkRules;
        ScanContext nextLibraryWide;
        EXPECT_FALSE(runStep(nextLibraryWide, {}, settings));
    }
} // namespace lms::scanner::tests
