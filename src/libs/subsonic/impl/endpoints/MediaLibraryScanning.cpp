/*
 * Copyright (C) 2020 Emeric Poupon
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

#include "MediaLibraryScanning.hpp"

#include "core/Service.hpp"
#include "core/String.hpp"
#include "services/scanner/IScannerService.hpp"
#include "services/recommendation/IRecommendationService.hpp"

#include "database/Session.hpp"
#include "database/objects/ScanSettings.hpp"
#include "database/objects/User.hpp"
#include "ParameterParsing.hpp"

namespace lms::api::subsonic::Scan
{
    using namespace scanner;

    namespace
    {
        std::string scanStepToString(ScanStep step)
        {
            switch (step)
            {
            case ScanStep::AssociateArtistImages: return "AssociateArtistImages";
            case ScanStep::AssociateExternalLyrics: return "AssociateExternalLyrics";
            case ScanStep::AssociatePlayListTracks: return "AssociatePlayListTracks";
            case ScanStep::AssociateReleaseImages: return "AssociateReleaseImages";
            case ScanStep::AssociateTrackImages: return "AssociateTrackImages";
            case ScanStep::CheckForDuplicatedFiles: return "CheckForDuplicatedFiles";
            case ScanStep::CheckForRemovedFiles: return "CheckForRemovedFiles";
            case ScanStep::Compact: return "Compact";
            case ScanStep::ComputeClusterStats: return "ComputeClusterStats";
            case ScanStep::Optimize: return "Optimize";
            case ScanStep::ReconciliateArtists: return "ReconciliateArtists";
            case ScanStep::RemoveOrphanedDbEntries: return "RemoveOrphanedDbEntries";
            case ScanStep::ReloadSimilarityEngine: return "ReloadSimilarityEngine";
            case ScanStep::ScanFiles: return "ScanFiles";
            case ScanStep::UpdateLibraryFields: return "UpdateLibraryFields";
            }
            return "Unknown";
        }

        Response::Node createStatusResponseNode(RequestContext& context)
        {
            Response::Node statusResponse;

            const IScannerService::Status scanStatus{ core::Service<IScannerService>::get()->getStatus() };

            statusResponse.setAttribute("scanning", scanStatus.currentState == IScannerService::State::InProgress);
            if (scanStatus.currentState == IScannerService::State::InProgress)
            {
                if (scanStatus.currentScanStepStats)
                {
                    statusResponse.setAttribute("step", scanStepToString(scanStatus.currentScanStepStats->currentStep));
                    statusResponse.setAttribute("stepIndex", scanStatus.currentScanStepStats->stepIndex);
                    statusResponse.setAttribute("stepCount", scanStatus.currentScanStepStats->stepCount);
                    statusResponse.setAttribute("count", scanStatus.currentScanStepStats->processedElems);
                    statusResponse.setAttribute("totalCount", scanStatus.currentScanStepStats->totalElems);
                }
            }

            if (scanStatus.lastCompleteScanStats)
            {
                Response::Node& lastScanNode{ statusResponse.createChild("lastScan") };
                lastScanNode.setAttribute("startTime", scanStatus.lastCompleteScanStats->startTime.toString().toUTF8());
                lastScanNode.setAttribute("stopTime", scanStatus.lastCompleteScanStats->stopTime.toString().toUTF8());
                lastScanNode.setAttribute("count", scanStatus.lastCompleteScanStats->getTotalFileCount());
                lastScanNode.setAttribute("errors", scanStatus.lastCompleteScanStats->errorsCount);
            }

            // Add some settings to the response if the user is an admin
            if (context.getUser()->isAdmin())
            {
                auto transaction{ context.getDbSession().createReadTransaction() };
                if (const db::ScanSettings::pointer settings{ db::ScanSettings::find(context.getDbSession()) })
                {
                    Response::Node& settingsNode{ statusResponse.createChild("scanSettings") };
                    settingsNode.setAttribute("updatePeriod", static_cast<int>(settings->getUpdatePeriod()));
                    settingsNode.setAttribute("updateStartTime", settings->getUpdateStartTime().toString().toUTF8());
                    settingsNode.setAttribute("similarityEngineType", static_cast<int>(settings->getSimilarityEngineType()));
                    settingsNode.setAttribute("skipSingleReleasePlayLists", settings->getSkipSingleReleasePlayLists());
                    settingsNode.setAttribute("allowMBIDArtistMerge", settings->getAllowMBIDArtistMerge());
                    settingsNode.setAttribute("artistImageFallbackToRelease", settings->getArtistImageFallbackToReleaseField());

                    auto addArray = [&](Response::Node::Key name, const auto& values) {
                        Response::Node& node{ settingsNode.createChild(name) };
                        for (const auto& value : values)
                            node.createChild("value").setValue(std::string_view{ value });
                    };

                    addArray("extraTagsToScan", settings->getExtraTagsToScan());
                    addArray("artistTagDelimiters", settings->getArtistTagDelimiters());
                    addArray("defaultTagDelimiters", settings->getDefaultTagDelimiters());
                    addArray("artistsToNotSplit", settings->getArtistsToNotSplit());
                }
            }

            return statusResponse;
        }
    } // namespace

    Response handleGetScanStatus(RequestContext& context)
    {
        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        response.addNode("scanStatus", createStatusResponseNode(context));

        return response;
    }

    Response handleStartScan(RequestContext& context)
    {
        if (context.getUser()->isAdmin())
        {
            scanner::ScanOptions scanOptions;
            if (auto fullScan = getParameterAs<std::string>(context.getParameters(), "fullScan"))
                scanOptions.fullScan = (*fullScan == "true");
            if (auto forceOptimize = getParameterAs<std::string>(context.getParameters(), "forceOptimize"))
                scanOptions.forceOptimize = (*forceOptimize == "true");
            if (auto compact = getParameterAs<std::string>(context.getParameters(), "compact"))
                scanOptions.compact = (*compact == "true");

            core::Service<IScannerService>::get()->requestImmediateScan(scanOptions);
        }

        Response response{ Response::createOkResponse(context.getServerProtocolVersion()) };
        response.addNode("scanStatus", createStatusResponseNode(context));

        return response;
    }

    Response handleUpdateScanSettings(RequestContext& context)
    {
        if (context.getUser()->isAdmin())
        {
            auto transaction{ context.getDbSession().createWriteTransaction() };
            db::ScanSettings::pointer settings{ db::ScanSettings::find(context.getDbSession()) };

            if (auto period = getParameterAs<std::string>(context.getParameters(), "updatePeriod"))
                settings.modify()->setUpdatePeriod(static_cast<db::ScanSettings::UpdatePeriod>(std::stoi(*period)));

            if (auto startTime = getParameterAs<std::string>(context.getParameters(), "updateStartTime"))
                settings.modify()->setUpdateStartTime(Wt::WTime::fromString(*startTime, "HH:mm:ss"));

            if (auto similarity = getParameterAs<std::string>(context.getParameters(), "similarityEngineType"))
                settings.modify()->setSimilarityEngineType(static_cast<db::ScanSettings::SimilarityEngineType>(std::stoi(*similarity)));

            if (auto skip = getParameterAs<std::string>(context.getParameters(), "skipSingleReleasePlayLists"))
                settings.modify()->setSkipSingleReleasePlayLists(*skip == "true");

            if (auto merge = getParameterAs<std::string>(context.getParameters(), "allowMBIDArtistMerge"))
                settings.modify()->setAllowMBIDArtistMerge(*merge == "true");

            if (auto fallback = getParameterAs<std::string>(context.getParameters(), "artistImageFallbackToRelease"))
                settings.modify()->setArtistImageFallbackToReleaseField(*fallback == "true");

            auto getArray = [&](const std::string& name) {
                std::vector<std::string_view> result;
                if (auto value = getParameterAs<std::string>(context.getParameters(), name))
                {
                    std::vector<std::string_view> tokens{ core::stringUtils::splitString(*value, '|') };
                    for (auto token : tokens)
                        if (!token.empty())
                            result.push_back(token);
                }
                return result;
            };

            if (getParameterAs<std::string>(context.getParameters(), "extraTagsToScan"))
            {
                auto tags = getArray("extraTagsToScan");
                settings.modify()->setExtraTagsToScan(tags);
            }

            if (getParameterAs<std::string>(context.getParameters(), "artistTagDelimiters"))
            {
                auto delimiters = getArray("artistTagDelimiters");
                settings.modify()->setArtistTagDelimiters(delimiters);
            }

            if (getParameterAs<std::string>(context.getParameters(), "defaultTagDelimiters"))
            {
                auto delimiters = getArray("defaultTagDelimiters");
                settings.modify()->setDefaultTagDelimiters(delimiters);
            }

            if (getParameterAs<std::string>(context.getParameters(), "artistsToNotSplit"))
            {
                auto artists = getArray("artistsToNotSplit");
                settings.modify()->setArtistsToNotSplit(artists);
            }

            core::Service<recommendation::IRecommendationService>::get()->load();
            core::Service<scanner::IScannerService>::get()->requestReload();
        }

        return handleGetScanStatus(context);
    }
} // namespace lms::api::subsonic::Scan
