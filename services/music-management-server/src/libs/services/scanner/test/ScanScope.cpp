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
#include <vector>

#include <unistd.h>

#include <gtest/gtest.h>

#include "core/IConfig.hpp"
#include "core/IJobScheduler.hpp"
#include "core/Service.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artist.hpp"
#include "database/objects/Artwork.hpp"
#include "database/objects/Cluster.hpp"
#include "database/objects/Image.hpp"
#include "database/objects/PlayListFile.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackArtistLink.hpp"

#include "FileScanners.hpp"
#include "ScanContext.hpp"
#include "ScannerSettings.hpp"
#include "scanners/IFileScanner.hpp"
#include "steps/ScanScope.hpp"
#include "steps/ScanStepAssociateTrackImages.hpp"
#include "steps/ScanStepComputeClusterStats.hpp"

// Bug report 141: a scoped scan recomputes what its folders can have changed, not the library.
// Names are distinct from the other test files' helpers: the release image builds with
// CMAKE_UNITY_BUILD, which merges the anonymous namespaces into one unit.
namespace lms::scanner::tests
{
    namespace
    {
        // Every setting at its default, as a config file without the keys would answer.
        class ScanScopeTestConfig final : public core::IConfig
        {
        private:
            std::string_view getString(std::string_view, std::string_view def) override { return def; }
            void visitStrings(std::string_view, std::function<void(std::string_view)> func, std::initializer_list<std::string_view> defs) override
            {
                for (std::string_view def : defs)
                    func(def);
            }
            std::filesystem::path getPath(std::string_view, const std::filesystem::path& def) override { return def; }
            unsigned long getULong(std::string_view, unsigned long def) override { return def; }
            long getLong(std::string_view, long def) override { return def; }
            bool getBool(std::string_view, bool def) override { return def; }
        };

        std::filesystem::path makeScanScopeTestDbPath()
        {
            static std::atomic<unsigned> counter{};
            return std::filesystem::temp_directory_path() / ("lms-test-scan-scope-" + std::to_string(::getpid()) + "-" + std::to_string(counter++) + ".db");
        }

        // /music/A and /music/B hold the two discs of release "Split", /music/C holds release
        // "Other" and /music/AB release "Prefix". Split has its own artist and genre; the other
        // two share theirs.
        class ScanScopeTest : public ::testing::Test
        {
        protected:
            ScanScopeTest()
                : _dbPath{ makeScanScopeTestDbPath() }
                , _db{ db::createDb(_dbPath) }
                , _session{ _db->getTLSSession() }
                , _jobScheduler{ core::createJobScheduler("test-scan-scope", 1) }
            {
                _session.prepareTablesIfNeeded();
                _session.createIndexesIfNeeded();

                auto transaction{ _session.createWriteTransaction() };

                const db::Release::pointer split{ _session.create<db::Release>("Split") };
                const db::Release::pointer other{ _session.create<db::Release>("Other") };
                const db::Release::pointer prefix{ _session.create<db::Release>("Prefix") };
                splitRelease = split->getId();
                otherRelease = other->getId();
                prefixRelease = prefix->getId();

                const db::Artist::pointer splitArtist{ _session.create<db::Artist>("Split Artist") };
                const db::Artist::pointer otherArtist{ _session.create<db::Artist>("Other Artist") };
                splitArtistId = splitArtist->getId();
                otherArtistId = otherArtist->getId();

                const db::ClusterType::pointer genreType{ _session.create<db::ClusterType>("GENRE") };
                const db::Cluster::pointer hardstyle{ _session.create<db::Cluster>(genreType, "Hardstyle") };
                const db::Cluster::pointer hardcore{ _session.create<db::Cluster>(genreType, "Hardcore") };
                hardstyleId = hardstyle->getId();
                hardcoreId = hardcore->getId();

                trackA1 = addTrack("/music/A/01.mp3", split, splitArtist, hardstyle);
                trackA2 = addTrack("/music/A/02.mp3", split, splitArtist, hardstyle);
                trackB1 = addTrack("/music/B/01.mp3", split, splitArtist, hardstyle);
                trackC1 = addTrack("/music/C/01.mp3", other, otherArtist, hardcore);
                // Same name prefix as /music/A, not under it.
                trackAB = addTrack("/music/AB/01.mp3", prefix, otherArtist, hardcore);

                const db::PlayListFile::pointer insidePlayList{ _session.create<db::PlayListFile>("/music/A/list.m3u") };
                const db::PlayListFile::pointer otherPlayList{ _session.create<db::PlayListFile>("/music/C/list.m3u") };
                playListA = insidePlayList->getId();
                playListC = otherPlayList->getId();
            }

            ~ScanScopeTest() override
            {
                _jobScheduler.reset();
                _db.reset();
                std::error_code ec;
                std::filesystem::remove(_dbPath, ec);
                std::filesystem::remove(_dbPath.string() + "-wal", ec);
                std::filesystem::remove(_dbPath.string() + "-shm", ec);
            }

            ScanScopeTest(const ScanScopeTest&) = delete;
            ScanScopeTest& operator=(const ScanScopeTest&) = delete;

            db::TrackId addTrack(const std::filesystem::path& path, const db::Release::pointer& release, const db::Artist::pointer& artist, const db::Cluster::pointer& genre)
            {
                db::Track::pointer track{ _session.create<db::Track>() };
                track.modify()->setAbsoluteFilePath(path);
                track.modify()->setRelease(release);
                track.modify()->setClusters({ genre });
                _session.create<db::TrackArtistLink>(track, artist, db::TrackArtistLinkType::Artist);
                return track->getId();
            }

            db::ArtworkId addImage(const std::filesystem::path& path)
            {
                auto transaction{ _session.createWriteTransaction() };
                const db::Image::pointer image{ _session.create<db::Image>(path) };
                return _session.create<db::Artwork>(image)->getId();
            }

            void setReleaseArtwork(db::ReleaseId releaseId, db::ArtworkId artworkId)
            {
                auto transaction{ _session.createWriteTransaction() };
                db::Release::updatePreferredArtwork(_session, releaseId, artworkId);
            }

            db::ArtworkId trackArtwork(db::TrackId trackId)
            {
                auto transaction{ _session.createReadTransaction() };
                return db::Track::find(_session, trackId)->getPreferredArtworkId();
            }

            std::size_t clusterTrackCount(db::ClusterId clusterId)
            {
                auto transaction{ _session.createReadTransaction() };
                return db::Cluster::find(_session, clusterId)->getTrackCount();
            }

            // One run of `Step`, as a scan with changes over `directories` would run it (none: a
            // library-wide scan).
            template<typename Step>
            void runStep(std::vector<std::filesystem::path> directories)
            {
                core::Service<core::IConfig> config{ std::make_unique<ScanScopeTestConfig>() };

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
                Step concreteStep{ params };
                IScanStep& step{ concreteStep };

                ScanContext context;
                context.scanOptions.scanDirectories = std::move(directories);
                context.stats.updates = 1;
                ASSERT_TRUE(step.needProcess(context));
                step.process(context);
                EXPECT_EQ(context.currentStepStats.processedElems, context.currentStepStats.totalElems);
            }

            db::Session& session() { return _session; }

            db::ReleaseId splitRelease;
            db::ReleaseId otherRelease;
            db::ReleaseId prefixRelease;
            db::ArtistId splitArtistId;
            db::ArtistId otherArtistId;
            db::ClusterId hardstyleId;
            db::ClusterId hardcoreId;
            db::TrackId trackA1;
            db::TrackId trackA2;
            db::TrackId trackB1;
            db::TrackId trackC1;
            db::TrackId trackAB;
            db::PlayListFileId playListA;
            db::PlayListFileId playListC;

        private:
            const std::filesystem::path _dbPath;
            std::unique_ptr<db::IDb> _db;
            db::Session& _session;
            std::unique_ptr<core::IJobScheduler> _jobScheduler;
        };
    } // namespace

    TEST(ScanScopeIdRanges, consecutiveIdsShareARangeAndAGapStartsANewOne)
    {
        const std::vector<db::TrackId> ids{ 3, 4, 5, 9, 10, 42 };
        const auto ranges{ toConsecutiveIdRanges<db::TrackId>(ids) };

        ASSERT_EQ(ranges.size(), 3);
        EXPECT_EQ(ranges[0].first, db::TrackId{ 3 });
        EXPECT_EQ(ranges[0].last, db::TrackId{ 5 });
        EXPECT_EQ(ranges[1].first, db::TrackId{ 9 });
        EXPECT_EQ(ranges[1].last, db::TrackId{ 10 });
        EXPECT_EQ(ranges[2].first, db::TrackId{ 42 });
        EXPECT_EQ(ranges[2].last, db::TrackId{ 42 });
    }

    TEST(ScanScopeIdRanges, aLongRunIsSplitAtTheMaximumSize)
    {
        std::vector<db::TrackId> ids;
        for (long long id{ 1 }; id <= 250; ++id)
            ids.emplace_back(id);

        const auto ranges{ toConsecutiveIdRanges<db::TrackId>(ids, 100) };

        ASSERT_EQ(ranges.size(), 3);
        EXPECT_EQ(ranges[0].last, db::TrackId{ 100 });
        EXPECT_EQ(ranges[1].first, db::TrackId{ 101 });
        EXPECT_EQ(ranges[2].last, db::TrackId{ 250 });
    }

    TEST(ScanScopeIdRanges, noIdsNoRanges)
    {
        EXPECT_TRUE(toConsecutiveIdRanges<db::TrackId>(std::vector<db::TrackId>{}).empty());
    }

    TEST_F(ScanScopeTest, coversTheFolderAndTheRestOfItsReleasesButNothingElse)
    {
        const std::vector<std::filesystem::path> directories{ "/music/A" };
        const std::optional<ScanScope> scope{ computeScanScope(session(), directories) };
        ASSERT_TRUE(scope);

        // B/01 is on the same release as A's tracks, so its artwork follows theirs.
        EXPECT_EQ(scope->tracks, (std::vector<db::TrackId>{ trackA1, trackA2, trackB1 }));
        EXPECT_EQ(scope->releases, (std::vector<db::ReleaseId>{ splitRelease }));
        EXPECT_EQ(scope->artists, (std::vector<db::ArtistId>{ splitArtistId }));
        EXPECT_EQ(scope->clusters, (std::vector<db::ClusterId>{ hardstyleId }));
        EXPECT_EQ(scope->playListFiles, (std::vector<db::PlayListFileId>{ playListA }));
    }

    TEST_F(ScanScopeTest, tooManyTracksMeansTheWholeLibrary)
    {
        const std::vector<std::filesystem::path> directories{ "/music/A" };
        // Two tracks under the folder, three with the rest of the release.
        EXPECT_FALSE(computeScanScope(session(), directories, 1));
        EXPECT_FALSE(computeScanScope(session(), directories, 2));
        EXPECT_TRUE(computeScanScope(session(), directories, 3));
    }

    TEST_F(ScanScopeTest, aFolderWithoutTracksHasAnEmptyScope)
    {
        const std::vector<std::filesystem::path> directories{ "/music/Gone" };
        const std::optional<ScanScope> scope{ computeScanScope(session(), directories) };
        ASSERT_TRUE(scope);
        EXPECT_TRUE(scope->tracks.empty());
        EXPECT_TRUE(scope->releases.empty());
        EXPECT_TRUE(scope->artists.empty());
        EXPECT_TRUE(scope->playListFiles.empty());
    }

    TEST_F(ScanScopeTest, scopedTrackArtworkLeavesTracksOutsideTheScopeAlone)
    {
        const db::ArtworkId splitCover{ addImage("/music/A/cover.jpg") };
        const db::ArtworkId otherCover{ addImage("/music/C/cover.jpg") };
        const db::ArtworkId prefixCover{ addImage("/music/AB/cover.jpg") };
        setReleaseArtwork(splitRelease, splitCover);
        setReleaseArtwork(otherRelease, otherCover);
        setReleaseArtwork(prefixRelease, prefixCover);

        runStep<ScanStepAssociateTrackImages>({ "/music/A" });

        EXPECT_EQ(trackArtwork(trackA1), splitCover);
        EXPECT_EQ(trackArtwork(trackA2), splitCover);
        EXPECT_EQ(trackArtwork(trackB1), splitCover); // same release, other folder
        EXPECT_FALSE(trackArtwork(trackC1).isValid());
        EXPECT_FALSE(trackArtwork(trackAB).isValid());

        // The library-wide scan still covers everything.
        runStep<ScanStepAssociateTrackImages>({});

        EXPECT_EQ(trackArtwork(trackC1), otherCover);
        EXPECT_EQ(trackArtwork(trackAB), prefixCover);
    }

    TEST_F(ScanScopeTest, scopedClusterStatsAlsoFixTheGenreATrackLeft)
    {
        runStep<ScanStepComputeClusterStats>({});
        EXPECT_EQ(clusterTrackCount(hardstyleId), 3);
        EXPECT_EQ(clusterTrackCount(hardcoreId), 2);

        // /music/C/01 is retagged from Hardcore to Hardstyle and a scan of /music/C reads it.
        // Hardstyle is in the scope through the track; Hardcore is not linked to anything in it
        // any more and is found by its stale count.
        {
            auto transaction{ session().createWriteTransaction() };
            db::Track::find(session(), trackC1).modify()->setClusters({ db::Cluster::find(session(), hardstyleId) });
        }

        runStep<ScanStepComputeClusterStats>({ "/music/C" });
        EXPECT_EQ(clusterTrackCount(hardstyleId), 4);
        EXPECT_EQ(clusterTrackCount(hardcoreId), 1);
    }
} // namespace lms::scanner::tests
