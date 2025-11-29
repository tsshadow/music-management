/*
 * Copyright (C) 2025 Emeric Poupon
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

#include "DownloadEpisodesStep.hpp"

#include <fstream>

#include "core/IConfig.hpp"
#include "core/ILogger.hpp"
#include "core/Service.hpp"
#include "core/http/IClient.hpp"

#include "audio/AudioTypes.hpp"
#include "audio/Exception.hpp"
#include "audio/IAudioFileInfo.hpp"
#include "audio/IAudioFileInfoParser.hpp"
#include "database/IDb.hpp"
#include "database/Session.hpp"
#include "database/objects/Podcast.hpp"
#include "database/objects/PodcastEpisode.hpp"

#include "Executor.hpp"
#include "Utils.hpp"

namespace lms::podcast
{
    namespace
    {
        db::ContainerType audioContainerToDbContainer(audio::ContainerType type)
        {
            switch (type)
            {
            case audio::ContainerType::AIFF:
                return db::ContainerType::AIFF;
            case audio::ContainerType::APE:
                return db::ContainerType::APE;
            case audio::ContainerType::ASF:
                return db::ContainerType::ASF;
            case audio::ContainerType::DSF:
                return db::ContainerType::DSF;
            case audio::ContainerType::FLAC:
                return db::ContainerType::FLAC;
            case audio::ContainerType::MP4:
                return db::ContainerType::MP4;
            case audio::ContainerType::MPC:
                return db::ContainerType::MPC;
            case audio::ContainerType::MPEG:
                return db::ContainerType::MPEG;
            case audio::ContainerType::Shorten:
                return db::ContainerType::Shorten;
            case audio::ContainerType::Ogg:
                return db::ContainerType::Ogg;
            case audio::ContainerType::TrueAudio:
                return db::ContainerType::TrueAudio;
            case audio::ContainerType::WAV:
                return db::ContainerType::WAV;
            case audio::ContainerType::WavPack:
                return db::ContainerType::WavPack;
            }

            return db::ContainerType::Unknown;
        }

        db::CodecType audioCodecToDbCodec(audio::CodecType type)
        {
            switch (type)
            {
            case audio::CodecType::AAC:
                return db::CodecType::AAC;
            case audio::CodecType::AC3:
                return db::CodecType::AC3;
            case audio::CodecType::ALAC:
                return db::CodecType::ALAC;
            case audio::CodecType::APE:
                return db::CodecType::APE;
            case audio::CodecType::DSD:
                return db::CodecType::DSD;
            case audio::CodecType::EAC3:
                return db::CodecType::EAC3;
            case audio::CodecType::FLAC:
                return db::CodecType::FLAC;
            case audio::CodecType::MP3:
                return db::CodecType::MP3;
            case audio::CodecType::MP4ALS:
                return db::CodecType::MP4ALS;
            case audio::CodecType::MPC7:
                return db::CodecType::MPC7;
            case audio::CodecType::MPC8:
                return db::CodecType::MPC8;
            case audio::CodecType::Opus:
                return db::CodecType::Opus;
            case audio::CodecType::PCM:
                return db::CodecType::PCM;
            case audio::CodecType::Shorten:
                return db::CodecType::Shorten;
            case audio::CodecType::TrueAudio:
                return db::CodecType::TrueAudio;
            case audio::CodecType::Vorbis:
                return db::CodecType::Vorbis;
            case audio::CodecType::WavPack:
                return db::CodecType::WavPack;
            case audio::CodecType::WMA1:
                return db::CodecType::WMA1;
            case audio::CodecType::WMA2:
                return db::CodecType::WMA2;
            case audio::CodecType::WMA9Pro:
                return db::CodecType::WMA9Pro;
            case audio::CodecType::WMA9Lossless:
                return db::CodecType::WMA9Lossless;
            }

            return db::CodecType::Unknown;
        }

        void updateEpisode(db::Session& session, db::PodcastEpisodeId episodeId, const std::filesystem::path& relativeFilePath, const audio::AudioProperties& audioProperties)
        {
            auto transaction{ session.createWriteTransaction() };

            db::PodcastEpisode::pointer dbEpisode{ db::PodcastEpisode::find(session, episodeId) };
            if (!dbEpisode)
                return; // may have been deleted by admin

            dbEpisode.modify()->setAudioRelativeFilePath(relativeFilePath);

            dbEpisode.modify()->setDuration(audioProperties.duration);
            dbEpisode.modify()->setContainer(audioContainerToDbContainer(audioProperties.container));
            dbEpisode.modify()->setCodec(audioCodecToDbCodec(audioProperties.codec));
            dbEpisode.modify()->setBitrate(audioProperties.bitrate);
            dbEpisode.modify()->setChannelCount(audioProperties.channelCount);
            dbEpisode.modify()->setSampleRate(audioProperties.sampleRate);
            dbEpisode.modify()->setBitsPerSample(audioProperties.bitsPerSample);
        }
    } // namespace

    DownloadEpisodesStep::DownloadEpisodesStep(RefreshContext& context, OnDoneCallback callback)
        : RefreshStep{ context, std::move(callback) }
        , _autoDownloadEpisodes{ core::Service<core::IConfig>::get()->getBool("podcast-auto-download-episodes", true) }
        , _autoDownloadEpisodesMaxAge{ core::Service<core::IConfig>::get()->getULong("podcast-auto-download-episodes-max-age-days", 30) }
        , _audioFileInfoParser{ audio::createAudioFileInfoParser(audio::AudioFileInfoParserBackend::FFmpeg) }
    {
    }

    DownloadEpisodesStep::~DownloadEpisodesStep() = default;

    core::LiteralString DownloadEpisodesStep::getName() const
    {
        return "Download episodes";
    }

    void DownloadEpisodesStep::run()
    {
        collectEpisodes();
        processNext();
    }

    void DownloadEpisodesStep::collectEpisodes()
    {
        const Wt::WDateTime now{ Wt::WDateTime::currentDateTime() };

        auto& session{ getDb().getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        db::PodcastEpisode::FindParameters params;

        _episodesToDownload.clear();
        db::PodcastEpisode::find(session, params, [&](const db::PodcastEpisode::pointer& episode) {
            if (!episode->getAudioRelativeFilePath().empty())
                return; // already downloaded

            switch (episode->getManualDownloadState())
            {
            case db::PodcastEpisode::ManualDownloadState::DownloadRequested:

                LMS_LOG(PODCAST, DEBUG, "Adding episode '" << episode->getTitle() << "' from podcast '" << episode->getPodcast()->getTitle() << "' to download queue (manually requested)");
                _episodesToDownload.push_back(episode->getId());

                break;

            case db::PodcastEpisode::ManualDownloadState::None:
                if (_autoDownloadEpisodes && now < episode->getPubDate().addDays(_autoDownloadEpisodesMaxAge.count()))
                {
                    LMS_LOG(PODCAST, DEBUG, "Adding episode '" << episode->getTitle() << "' from podcast '" << episode->getPodcast()->getTitle() << "' to download queue (auto-download enabled)");
                    _episodesToDownload.push_back(episode->getId());
                }
                break;

            case db::PodcastEpisode::ManualDownloadState::DeleteRequested:
                break;
            }
        });
    }

    void DownloadEpisodesStep::processNext()
    {
        getExecutor().post([this] {
            if (_episodesToDownload.empty())
            {
                LMS_LOG(PODCAST, DEBUG, "All pending episodes downloaded");
                onDone();
                return;
            }

            const db::PodcastEpisodeId podcastEpisodeId{ _episodesToDownload.front() };
            _episodesToDownload.pop_front();
            process(podcastEpisodeId);
        });
    }

    void DownloadEpisodesStep::process(db::PodcastEpisodeId episodeId)
    {
        auto& session{ getDb().getTLSSession() };
        auto transaction{ session.createReadTransaction() };

        const db::PodcastEpisode::pointer episode{ db::PodcastEpisode::find(session, episodeId) };
        if (!episode)
        {
            LMS_LOG(PODCAST, DEBUG, "Cannot find episode: removed?"); // TODO if removed, need to keep it in the db to check for new episodes...
            processNext();
            return;
        }

        const std::string randomName{ utils::generateRandomFileName() };
        const std::filesystem::path tmpFilePath{ getTmpCachePath() / randomName };
        const std::filesystem::path finalFilePath{ getCachePath() / randomName };
        LMS_LOG(PODCAST, DEBUG, "Downloading episode '" << episode->getTitle() << "' from '" << episode->getEnclosureUrl() << "' in tmp file '" << tmpFilePath << "'");

        core::http::ClientGETRequestParameters params;
        const std::string url{ episode->getEnclosureUrl() };
        params.relativeUrl = url;
        params.onFailureFunc = [this, episode] {
            LMS_LOG(PODCAST, ERROR, "Failed to download podcast episode from '" << episode->getEnclosureUrl() << "'");
            processNext();
        };
        params.onChunkReceived = [url, tmpFilePath](std::span<const std::byte> chunk) {
            std::ofstream file{ tmpFilePath, std::ios::binary | std::ios::app };
            if (!file)
            {
                std::error_code ec{ errno, std::generic_category() };
                LMS_LOG(PODCAST, ERROR, "Failed to open file '" << tmpFilePath << "' for writing: " << ec.message());
                return core::http::ClientGETRequestParameters::ChunckReceivedResult::Abort;
            }

            // check write status
            file.write(reinterpret_cast<const char*>(chunk.data()), chunk.size());
            if (!file)
            {
                std::error_code ec{ errno, std::generic_category() };
                LMS_LOG(PODCAST, ERROR, "Failed to write to file '" << tmpFilePath << "': " << ec.message());
                return core::http::ClientGETRequestParameters::ChunckReceivedResult::Abort;
            }

            return core::http::ClientGETRequestParameters::ChunckReceivedResult::Continue;
        };
        params.onSuccessFunc = [=, this]([[maybe_unused]] const Wt::Http::Message& msg) {
            assert(msg.body().empty());
            getExecutor().post([=, this] {
                LMS_LOG(PODCAST, DEBUG, "Download episode from '" << url << "' complete");

                try
                {
                    audio::AudioFileInfoParseOptions options;
                    options.audioPropertiesReadStyle = audio::AudioFileInfoParseOptions::AudioPropertiesReadStyle::Average;
                    options.readImages = false;
                    options.readTags = false;

                    const auto audioFileInfo{ _audioFileInfoParser->parse(tmpFilePath, options) };
                    const auto* audioProperties{ audioFileInfo->getAudioProperties() };
                    if (audioProperties)
                    {
                        std::error_code ec;
                        std::filesystem::rename(tmpFilePath, finalFilePath, ec);
                        if (ec)
                        {
                            LMS_LOG(PODCAST, ERROR, "Failed to rename temp file " << tmpFilePath << " to " << finalFilePath << ": " << ec.message());
                        }
                        else
                        {
                            updateEpisode(getDb().getTLSSession(), episodeId, randomName, *audioProperties);
                            LMS_LOG(PODCAST, INFO, "Downloaded episode '" << episode->getTitle() << "'");
                        }
                    }
                    else
                    {
                        LMS_LOG(PODCAST, WARNING, "Failed to get audio properties from downloaded episode from '" << url << "'");
                    }
                }
                catch (const audio::Exception& e)
                {
                    LMS_LOG(PODCAST, WARNING, "Failed to parse downloaded episode from '" << url << "': " << e.what());
                }

                processNext();
            });
        };
        params.onAbortFunc = [this] {
            onAbort();
        };

        LMS_LOG(PODCAST, DEBUG, "Downloading episode from '" << url << "'...");
        getClient().sendGETRequest(std::move(params));
    }
} // namespace lms::podcast