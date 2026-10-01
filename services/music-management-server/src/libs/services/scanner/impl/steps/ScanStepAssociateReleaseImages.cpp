/*
 * Copyright (C) 2024 Emeric Poupon
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

#include "ScanStepAssociateReleaseImages.hpp"

#include <cassert>
#include <deque>
#include <filesystem>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "core/IConfig.hpp"
#include "core/IJob.hpp"
#include "core/ILogger.hpp"
#include "core/Path.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Artwork.hpp"
#include "database/objects/Directory.hpp"
#include "database/objects/Image.hpp"
#include "database/objects/Release.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/TrackEmbeddedImage.hpp"

#include "JobQueue.hpp"
#include "ScanContext.hpp"
#include "ScanScope.hpp"

namespace lms::scanner
{
    namespace
    {
        struct ReleaseArtworkAssociation
        {
            db::ReleaseId releaseId;
            db::ArtworkId preferredArtworkId;
        };
        using ReleaseArtworkAssociationContainer = std::deque<ReleaseArtworkAssociation>;

        struct SearchReleaseArtworkParams
        {
            const ReleaseArtworkRules* rules{}; // never null
        };

        // The directories holding the release's tracks, and the deepest one they share: expect a
        // layout like Artist/Release/CD1/..., Artist/Release/CD2/..., Artist/Release/cover.jpg.
        struct ReleaseDirectories
        {
            std::optional<std::filesystem::path> commonPath; // only for a release spread over several directories
            std::set<std::filesystem::path> paths;
        };

        ReleaseDirectories findReleaseDirectories(db::Session& session, const db::Release::pointer& release)
        {
            ReleaseDirectories res;

            db::Directory::FindParameters params;
            params.setRelease(release->getId());
            db::Directory::find(session, params, [&](const db::Directory::pointer& directory) {
                res.paths.insert(directory->getAbsolutePath());
            });

            if (res.paths.size() > 1)
                res.commonPath = core::pathUtils::getLongestCommonPath(std::cbegin(res.paths), std::cend(res.paths));

            return res;
        }

        // Tries `findInDirectory` on the shared parent first, then on each directory in turn.
        template<typename FindInDirectory>
        db::Artwork::pointer searchReleaseDirectories(const ReleaseDirectories& directories, FindInDirectory findInDirectory)
        {
            db::Artwork::pointer artwork;

            if (directories.commonPath)
                artwork = findInDirectory(*directories.commonPath);

            for (const std::filesystem::path& releasePath : directories.paths)
            {
                if (artwork)
                    break;
                artwork = findInDirectory(releasePath);
            }

            return artwork;
        }

        db::Artwork::pointer findPreferredImageInDirectory(db::Session& session, const SearchReleaseArtworkParams& searchParams, const std::filesystem::path& directoryPath)
        {
            db::Artwork::pointer artwork;

            const db::Directory::pointer directory{ db::Directory::find(session, directoryPath) };
            if (directory) // may not exist for releases that are split on different media libraries
            {
                for (std::string_view fileStem : searchParams.rules->preferredFileNames)
                {
                    db::Image::FindParameters params;
                    params.setDirectory(directory->getId());
                    params.setFileStem(fileStem, db::Image::FindParameters::ProcessWildcards{ true }); // no need to sanitize here, user is responsible for providing sanitized file stems in conf file

                    db::Image::find(session, params, [&](const db::Image::pointer& image) {
                        if (!artwork)
                            artwork = db::Artwork::find(session, image->getId());
                    });

                    if (artwork)
                        break;
                }
            }

            return artwork;
        }

        // The image none of the preferred names matched: a scene release's
        // `00-artist_-_title-(cat)-web-2026.jpg`, or the only image there is (bug report 144).
        db::Artwork::pointer findFallbackImageInDirectory(db::Session& session, const SearchReleaseArtworkParams& searchParams, const std::filesystem::path& directoryPath)
        {
            const db::Directory::pointer directory{ db::Directory::find(session, directoryPath) };
            if (!directory)
                return db::Artwork::pointer{};

            std::vector<db::ImageId> imageIds;
            std::vector<std::string> stems;
            db::Image::find(session, db::Image::FindParameters{}.setDirectory(directory->getId()), [&](const db::Image::pointer& image) {
                imageIds.push_back(image->getId());
                stems.emplace_back(image->getFileStem());
            });

            const std::optional<std::size_t> picked{ pickFallbackReleaseImage(*searchParams.rules, stems) };
            if (!picked)
                return db::Artwork::pointer{};

            return db::Artwork::find(session, imageIds.at(*picked));
        }

        db::Artwork::pointer computePreferredReleaseImage(db::Session& session, const SearchReleaseArtworkParams& searchParams, const db::Release::pointer& release, const ReleaseDirectories& directories)
        {
            db::Artwork::pointer artwork;

            const auto mbid{ release->getMBID() };
            if (mbid)
            {
                // Find anywhere, since it is suppoed to be unique!
                db::Image::find(session, db::Image::FindParameters{}.setFileStem(mbid->getAsString()), [&](const db::Image::pointer& image) {
                    if (!artwork)
                        artwork = db::Artwork::find(session, image->getId());
                });
            }

            if (!artwork)
            {
                artwork = searchReleaseDirectories(directories, [&](const std::filesystem::path& path) {
                    return findPreferredImageInDirectory(session, searchParams, path);
                });
            }

            return artwork;
        }

        db::Artwork::pointer findEmbeddedReleaseImage(db::Session& session, const db::Release::pointer& release, core::media::ImageType imageType)
        {
            db::Artwork::pointer artwork;

            db::TrackEmbeddedImage::FindParameters params;
            params.setRelease(release->getId());
            params.setImageType(imageType);
            params.setSortMethod(db::TrackEmbeddedImageSortMethod::DiscNumberThenTrackNumberThenSizeDesc);
            db::TrackEmbeddedImage::find(session, params, [&](const db::TrackEmbeddedImage::pointer& image) {
                if (!artwork)
                    artwork = db::Artwork::find(session, image->getId());
            });

            return artwork;
        }

        // In order: an image named after the release's MBID or one of the preferred names, an
        // embedded front cover, the fallback image of the directory (an explicit front cover in
        // the file stays ahead of a guess from a file name), an embedded disc image, and finally
        // an embedded image of another type, as some tracks are badly tagged.
        db::Artwork::pointer computePreferredReleaseArtwork(db::Session& session, const SearchReleaseArtworkParams& searchParams, const db::Release::pointer& release)
        {
            const ReleaseDirectories directories{ findReleaseDirectories(session, release) };

            db::Artwork::pointer artwork{ computePreferredReleaseImage(session, searchParams, release, directories) };

            if (!artwork)
                artwork = findEmbeddedReleaseImage(session, release, core::media::ImageType::FrontCover);

            if (!artwork)
            {
                artwork = searchReleaseDirectories(directories, [&](const std::filesystem::path& path) {
                    return findFallbackImageInDirectory(session, searchParams, path);
                });
            }

            if (!artwork)
                artwork = findEmbeddedReleaseImage(session, release, core::media::ImageType::Media);

            if (!artwork)
                artwork = findEmbeddedReleaseImage(session, release, core::media::ImageType::Other);

            return artwork;
        }

        void updateReleasePreferredArtwork(db::Session& session, const ReleaseArtworkAssociation& releaseArtworkAssociation)
        {
            db::Release::updatePreferredArtwork(session, releaseArtworkAssociation.releaseId, releaseArtworkAssociation.preferredArtworkId);
        }

        void updateReleasePreferredArtworks(db::Session& session, ReleaseArtworkAssociationContainer& imageAssociations, bool forceFullBatch)
        {
            constexpr std::size_t writeBatchSize{ 50 };

            while ((forceFullBatch && imageAssociations.size() >= writeBatchSize) || !imageAssociations.empty())
            {
                auto transaction{ session.createWriteTransaction() };

                for (std::size_t i{}; !imageAssociations.empty() && i < writeBatchSize; ++i)
                {
                    updateReleasePreferredArtwork(session, imageAssociations.front());
                    imageAssociations.pop_front();
                }
            }
        }

        bool fetchNextReleaseIdRange(db::Session& session, db::ReleaseId& lastRetrievedId, db::IdRange<db::ReleaseId>& idRange)
        {
            constexpr std::size_t readBatchSize{ 100 };

            auto transaction{ session.createReadTransaction() };

            idRange = db::Release::findNextIdRange(session, lastRetrievedId, readBatchSize);
            lastRetrievedId = idRange.last;

            return idRange.isValid();
        }

        class ComputeReleaseArtworkAssociationsJob : public core::IJob
        {
        public:
            ComputeReleaseArtworkAssociationsJob(db::IDb& db, const SearchReleaseArtworkParams& searchParams, db::IdRange<db::ReleaseId> artistIdRange)
                : _db{ db }
                , _searchParams{ searchParams }
                , _artistIdRange{ artistIdRange }
            {
            }

            std::span<const ReleaseArtworkAssociation> getAssociations() const { return _associations; }
            std::size_t getProcessedReleaseCount() const { return _processedReleaseCount; }

        private:
            core::LiteralString getName() const override { return "Associate Release Artworks"; }
            void run() override
            {
                auto& session{ _db.getTLSSession() };
                auto transaction{ session.createReadTransaction() };

                db::Release::find(session, _artistIdRange, [this, &session](const db::Release::pointer& release) {
                    const db::Artwork::pointer preferredArtwork{ computePreferredReleaseArtwork(session, _searchParams, release) };

                    if (release->getPreferredArtwork() != preferredArtwork)
                    {
                        _associations.push_back(ReleaseArtworkAssociation{ release->getId(), preferredArtwork ? preferredArtwork->getId() : db::ArtworkId{} });

                        if (preferredArtwork)
                            LMS_LOG(DBUPDATER, DEBUG, "Updating preferred artwork for release '" << release->getName() << "' with image in " << preferredArtwork->getAbsoluteFilePath());
                        else
                            LMS_LOG(DBUPDATER, DEBUG, "Removing preferred artwork from release '" << release->getName() << "'");
                    }

                    _processedReleaseCount++;
                });
            }

            db::IDb& _db;
            const SearchReleaseArtworkParams& _searchParams;
            db::IdRange<db::ReleaseId> _artistIdRange;
            std::vector<ReleaseArtworkAssociation> _associations;
            std::size_t _processedReleaseCount{};
        };

    } // namespace

    ScanStepAssociateReleaseImages::ScanStepAssociateReleaseImages(InitParams& initParams)
        : ScanStepBase{ initParams }
        , _rules{ readReleaseArtworkRules() }
    {
    }

    bool ScanStepAssociateReleaseImages::needProcess(const ScanContext& context) const
    {
        return context.stats.getChangesCount() > 0 || releaseArtworkRulesChanged(context);
    }

    void ScanStepAssociateReleaseImages::process(ScanContext& context)
    {
        auto& session{ _db.getTLSSession() };
        const ScanScope* scope{ getScanScope(context) };

        if (scope)
        {
            context.currentStepStats.totalElems = scope->releases.size();
        }
        else
        {
            auto transaction{ session.createReadTransaction() };
            context.currentStepStats.totalElems = db::Release::getCount(session);
        }

        const SearchReleaseArtworkParams searchParams{
            .rules = &_rules,
        };

        ReleaseArtworkAssociationContainer releaseArtworkAssociations;
        auto processJobsDone = [&](std::span<std::unique_ptr<core::IJob>> jobs) {
            if (_abortScan)
                return;

            for (const auto& job : jobs)
            {
                const auto& associationJob{ static_cast<const ComputeReleaseArtworkAssociationsJob&>(*job) };
                const auto& artistAssociations{ associationJob.getAssociations() };

                releaseArtworkAssociations.insert(std::end(releaseArtworkAssociations), std::cbegin(artistAssociations), std::cend(artistAssociations));

                context.currentStepStats.processedElems += associationJob.getProcessedReleaseCount();
            }

            updateReleasePreferredArtworks(session, releaseArtworkAssociations, true);
            _progressCallback(context.currentStepStats);
        };

        JobQueue queue{ getJobScheduler(), 20, processJobsDone, 1, 0.85F };

        if (scope)
        {
            // A scoped scan: only the releases of its tracks (bug report 141).
            for (const db::IdRange<db::ReleaseId>& releaseIdRange : toConsecutiveIdRanges<db::ReleaseId>(scope->releases))
                queue.push(std::make_unique<ComputeReleaseArtworkAssociationsJob>(_db, searchParams, releaseIdRange));
        }
        else
        {
            db::ReleaseId lastRetrievedReleaseId{};
            db::IdRange<db::ReleaseId> artistIdRange;
            while (fetchNextReleaseIdRange(session, lastRetrievedReleaseId, artistIdRange))
                queue.push(std::make_unique<ComputeReleaseArtworkAssociationsJob>(_db, searchParams, artistIdRange));
        }

        queue.finish();

        // process all remaining associations
        updateReleasePreferredArtworks(session, releaseArtworkAssociations, false);
    }
} // namespace lms::scanner
