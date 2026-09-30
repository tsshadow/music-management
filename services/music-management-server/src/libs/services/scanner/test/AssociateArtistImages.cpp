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
#include <memory>
#include <string>
#include <string_view>

#include <unistd.h>

#include <Wt/Dbo/Dbo.h>
#include <gtest/gtest.h>

#include "core/IConfig.hpp"
#include "core/IJobScheduler.hpp"
#include "core/Service.hpp"
#include "core/UUID.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/Artwork.hpp"
#include "database/objects/Image.hpp"

#include "FileScanners.hpp"
#include "ScanContext.hpp"
#include "ScannerSettings.hpp"
#include "scanners/IFileScanner.hpp"
#include "steps/ScanStepAssociateArtistImages.hpp"

// Bug report 139: LMS's artist-image association must keep a portrait music-manager chose.
// Names here are deliberately distinct from the helpers of the other test files: the release
// image builds with CMAKE_UNITY_BUILD, which merges the anonymous namespaces into one unit.
namespace lms::scanner::tests
{
    namespace
    {
        // Answers `artist-image-managed-directory` and falls back to the default for the rest,
        // the way a config file without those keys would.
        class PortraitTestConfig final : public core::IConfig
        {
        public:
            explicit PortraitTestConfig(std::filesystem::path managedDirectory)
                : _managedDirectory{ std::move(managedDirectory) }
            {
            }

        private:
            std::string_view getString(std::string_view, std::string_view def) override { return def; }
            void visitStrings(std::string_view, std::function<void(std::string_view)> func, std::initializer_list<std::string_view> defs) override
            {
                for (std::string_view def : defs)
                    func(def);
            }
            std::filesystem::path getPath(std::string_view setting, const std::filesystem::path& def) override
            {
                return setting == "artist-image-managed-directory" ? _managedDirectory : def;
            }
            unsigned long getULong(std::string_view, unsigned long def) override { return def; }
            long getLong(std::string_view, long def) override { return def; }
            bool getBool(std::string_view, bool def) override { return def; }

            const std::filesystem::path _managedDirectory;
        };

        std::filesystem::path makePortraitTestDbPath()
        {
            static std::atomic<unsigned> counter{};
            return std::filesystem::temp_directory_path() / ("lms-test-artist-portraits-" + std::to_string(::getpid()) + "-" + std::to_string(counter++) + ".db");
        }

        const core::UUID portraitTestMbid{ *core::UUID::fromString("0bdb5fb3-b2d1-4f07-9d34-4bd2d6d8b1e4") };

        // Where LMS's own choice for the artist lives: an image named after its MBID.
        std::filesystem::path portraitTestMbidImagePath()
        {
            return std::filesystem::path{ "/music/Some Label" } / (std::string{ portraitTestMbid.getAsString() } + ".jpg");
        }

        class AssociateArtistImagesTest : public ::testing::Test
        {
        protected:
            AssociateArtistImagesTest()
                : _dbPath{ makePortraitTestDbPath() }
                , _db{ db::createDb(_dbPath) }
                , _session{ _db->getTLSSession() }
                , _jobScheduler{ core::createJobScheduler("test-portraits", 1) }
            {
                _session.prepareTablesIfNeeded();
                _session.createIndexesIfNeeded();

                // Counts every write to an artist's pointer, so a test can prove a scan that
                // changes nothing writes nothing (bug report 132).
                auto transaction{ _session.createWriteTransaction() };
                _session.execute("CREATE TABLE test_artwork_writes (artist_id INTEGER)");
                _session.execute("CREATE TRIGGER test_count_artwork_writes AFTER UPDATE OF preferred_artwork_id ON artist BEGIN INSERT INTO test_artwork_writes VALUES (NEW.id); END");
            }

            ~AssociateArtistImagesTest() override
            {
                _jobScheduler.reset();
                _db.reset();
                std::error_code ec;
                std::filesystem::remove(_dbPath, ec);
                std::filesystem::remove(_dbPath.string() + "-wal", ec);
                std::filesystem::remove(_dbPath.string() + "-shm", ec);
            }

            AssociateArtistImagesTest(const AssociateArtistImagesTest&) = delete;
            AssociateArtistImagesTest& operator=(const AssociateArtistImagesTest&) = delete;

            // One run of the step, as a scan with changes would run it.
            void runStep(const std::filesystem::path& managedDirectory)
            {
                core::Service<core::IConfig> config{ std::make_unique<PortraitTestConfig>(managedDirectory) };

                const ScannerSettings settings{};
                bool abortScan{};
                FileScanners fileScanners;
                const std::filesystem::path cachePath{ "/tmp" };
                ScanStepBase::InitParams params{
                    .jobScheduler = *_jobScheduler,
                    .settings = settings,
                    .lastScanSettings = nullptr,
                    .progressCallback = [](const ScanStepStats&) {},
                    .abortScan = abortScan,
                    .db = *_db,
                    .fileScanners = fileScanners,
                    .cachePath = cachePath,
                };
                ScanStepAssociateArtistImages concreteStep{ params };
                IScanStep& step{ concreteStep };

                ScanContext context;
                context.stats.updates = 1;
                ASSERT_TRUE(step.needProcess(context));
                step.process(context);
                EXPECT_EQ(context.currentStepStats.processedElems, context.currentStepStats.totalElems);
            }

            db::ArtworkId addImage(const std::filesystem::path& path)
            {
                auto transaction{ _session.createWriteTransaction() };
                const db::Image::pointer image{ _session.create<db::Image>(path) };
                return _session.create<db::Artwork>(image)->getId();
            }

            db::ArtistId addArtist(const std::string& name, db::ArtworkId artwork)
            {
                auto transaction{ _session.createWriteTransaction() };
                const db::Artist::pointer artist{ _session.create<db::Artist>(name, portraitTestMbid) };
                if (artwork.isValid())
                    db::Artist::updatePreferredArtwork(_session, artist->getId(), artwork);
                return artist->getId();
            }

            db::ArtworkId preferredArtwork(db::ArtistId artistId)
            {
                auto transaction{ _session.createReadTransaction() };
                return db::Artist::find(_session, artistId)->getPreferredArtworkId();
            }

            void removeImageOf(db::ArtworkId artworkId)
            {
                // What ScanStepCheckForRemovedFiles does for a file that is gone.
                auto transaction{ _session.createWriteTransaction() };
                db::Artwork::find(_session, artworkId)->getImage().remove();
            }

            long long artworkWrites()
            {
                auto transaction{ _session.createReadTransaction() };
                return _session.getDboSession()->query<long long>("SELECT COUNT(*) FROM test_artwork_writes").resultValue();
            }

            const std::filesystem::path managedDirectory{ "/music/artists" };

        private:
            const std::filesystem::path _dbPath;
            std::unique_ptr<db::IDb> _db;
            db::Session& _session;
            std::unique_ptr<core::IJobScheduler> _jobScheduler;
        };
    } // namespace

    TEST_F(AssociateArtistImagesTest, artistWithAManagedPortraitKeepsIt)
    {
        // LMS's own choice would be the image named after the artist's MBID.
        addImage(portraitTestMbidImagePath());
        const db::ArtworkId portrait{ addImage("/music/artists/12/spotify-0123abcd.jpg") };
        const db::ArtistId artist{ addArtist("Artist", portrait) };
        const long long writesBefore{ artworkWrites() };

        runStep(managedDirectory);

        EXPECT_EQ(preferredArtwork(artist), portrait);
        EXPECT_EQ(artworkWrites(), writesBefore) << "keeping a portrait must not write the artist";
    }

    TEST_F(AssociateArtistImagesTest, artistWithoutAManagedPortraitGetsTheStepsChoice)
    {
        const db::ArtworkId mbidImage{ addImage(portraitTestMbidImagePath()) };
        const db::ArtistId artist{ addArtist("Artist", db::ArtworkId{}) };

        runStep(managedDirectory);
        EXPECT_EQ(preferredArtwork(artist), mbidImage);

        // Settled: the next scan finds nothing to change and writes nothing.
        const long long writesBefore{ artworkWrites() };
        runStep(managedDirectory);
        EXPECT_EQ(preferredArtwork(artist), mbidImage);
        EXPECT_EQ(artworkWrites(), writesBefore);
    }

    TEST_F(AssociateArtistImagesTest, artistPointingOutsideTheManagedFolderIsRecomputedAsBefore)
    {
        const db::ArtworkId mbidImage{ addImage(portraitTestMbidImagePath()) };
        const db::ArtworkId cover{ addImage("/music/Some Label/CAT001/cover.jpg") };
        // A sibling folder whose name merely starts with the managed one is not inside it.
        const db::ArtworkId lookalike{ addImage("/music/artists-old/12/spotify-0123abcd.jpg") };
        const db::ArtistId onCover{ addArtist("On cover", cover) };
        const db::ArtistId onLookalike{ addArtist("On lookalike", lookalike) };

        runStep(managedDirectory);

        EXPECT_EQ(preferredArtwork(onCover), mbidImage);
        EXPECT_EQ(preferredArtwork(onLookalike), mbidImage);
    }

    TEST_F(AssociateArtistImagesTest, artistWhoseManagedPortraitWasRemovedGetsANewChoice)
    {
        const db::ArtworkId mbidImage{ addImage(portraitTestMbidImagePath()) };
        const db::ArtworkId portrait{ addImage("/music/artists/12/spotify-0123abcd.jpg") };
        const db::ArtistId artist{ addArtist("Artist", portrait) };

        removeImageOf(portrait);
        ASSERT_FALSE(preferredArtwork(artist).isValid()) << "the image's removal cascades to the artist's pointer";

        runStep(managedDirectory);

        EXPECT_EQ(preferredArtwork(artist), mbidImage);
    }

    TEST_F(AssociateArtistImagesTest, withoutAManagedFolderConfiguredEveryArtistIsRecomputed)
    {
        const db::ArtworkId mbidImage{ addImage(portraitTestMbidImagePath()) };
        const db::ArtworkId portrait{ addImage("/music/artists/12/spotify-0123abcd.jpg") };
        const db::ArtistId artist{ addArtist("Artist", portrait) };

        runStep(std::filesystem::path{});

        EXPECT_EQ(preferredArtwork(artist), mbidImage);
    }

    TEST_F(AssociateArtistImagesTest, aRelativeManagedFolderIsIgnored)
    {
        const db::ArtworkId mbidImage{ addImage(portraitTestMbidImagePath()) };
        const db::ArtworkId portrait{ addImage("/music/artists/12/spotify-0123abcd.jpg") };
        const db::ArtistId artist{ addArtist("Artist", portrait) };

        runStep("music/artists");

        EXPECT_EQ(preferredArtwork(artist), mbidImage);
    }
} // namespace lms::scanner::tests
