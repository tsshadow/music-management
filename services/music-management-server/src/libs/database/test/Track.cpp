/*
 * Copyright (C) 2021 Emeric Poupon
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

#include "Common.hpp"

#include <algorithm>
#include <filesystem>
#include <iostream>
#include <set>
#include <vector>

#include <Wt/Dbo/SqlConnection.h>
#include <Wt/Dbo/SqlStatement.h>
#include <Wt/Dbo/Transaction.h>

#include "database/objects/Artwork.hpp"
#include "database/objects/Image.hpp"
#include "database/objects/RatedTrack.hpp"
#include "database/objects/User.hpp"

namespace lms::db::tests
{
    using ScopedArtwork = ScopedEntity<db::Artwork>;
    using ScopedImage = ScopedEntity<db::Image>;
    using ScopedLabel = ScopedEntity<db::Label>;

    TEST_F(DatabaseFixture, Track)
    {
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(Track::find(session, Track::FindParameters{}).results.size(), 0);
            EXPECT_EQ(Track::findIds(session, Track::FindParameters{}).results.size(), 0);
            EXPECT_EQ(Track::getCount(session), 0);
            EXPECT_FALSE(Track::exists(session, 0));

            {
                bool visited{};
                Track::find(session, Track::FindParameters{}, [&](const Track::pointer&) { visited = true; });
                EXPECT_FALSE(visited);
            }
        }

        ScopedTrack track{ session };

        {
            auto transaction{ session.createReadTransaction() };

            EXPECT_EQ(Track::find(session, Track::FindParameters{}).results.size(), 1);
            EXPECT_EQ(Track::getCount(session), 1);
            EXPECT_TRUE(Track::exists(session, track.getId()));
            auto myTrack{ Track::find(session, track.getId()) };
            ASSERT_TRUE(myTrack);
            EXPECT_EQ(myTrack->getId(), track.getId());

            {
                bool visited{};
                Track::find(session, Track::FindParameters{}, [&](const Track::pointer& t) {
                    visited = true;
                    EXPECT_EQ(t->getId(), track.getId());
                });
                EXPECT_TRUE(visited);
            }
        }
    }

    TEST_F(DatabaseFixture, Track_findByRangedIdBased)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };
        ScopedTrack track3{ session };
        ScopedMediaLibrary library{ session, "MyLibrary", "/root" };
        ScopedMediaLibrary otherLibrary{ session, "OtherLibrary", "/otherRoot" };

        {
            auto transaction{ session.createWriteTransaction() };
            track2.get().modify()->setMediaLibrary(library.get());
        }

        {
            auto transaction{ session.createReadTransaction() };

            TrackId lastRetrievedTrackId;
            std::vector<Track::pointer> visitedTracks;
            Track::find(session, lastRetrievedTrackId, 10, [&](const Track::pointer& track) {
                visitedTracks.push_back(track);
            });
            ASSERT_EQ(visitedTracks.size(), 3);
            EXPECT_EQ(visitedTracks[0]->getId(), track1.getId());
            EXPECT_EQ(visitedTracks[1]->getId(), track2.getId());
            EXPECT_EQ(visitedTracks[2]->getId(), track3.getId());
            EXPECT_EQ(lastRetrievedTrackId, track3.getId());
        }

        {
            auto transaction{ session.createReadTransaction() };

            TrackId lastRetrievedTrackId{ track1.getId() };
            std::vector<Track::pointer> visitedTracks;
            Track::find(session, lastRetrievedTrackId, 1, [&](const Track::pointer& track) {
                visitedTracks.push_back(track);
            });
            ASSERT_EQ(visitedTracks.size(), 1);
            EXPECT_EQ(visitedTracks[0]->getId(), track2.getId());
            EXPECT_EQ(lastRetrievedTrackId, track2.getId());
        }

        {
            auto transaction{ session.createReadTransaction() };

            TrackId lastRetrievedTrackId{ track1.getId() };
            std::vector<Track::pointer> visitedTracks;
            Track::find(session, lastRetrievedTrackId, 0, [&](const Track::pointer& track) {
                visitedTracks.push_back(track);
            });
            ASSERT_EQ(visitedTracks.size(), 0);
            EXPECT_EQ(lastRetrievedTrackId, track1.getId());
        }

        {
            auto transaction{ session.createReadTransaction() };

            TrackId lastRetrievedTrackId{};
            std::vector<Track::pointer> visitedTracks;
            Track::find(
                session, lastRetrievedTrackId, 10, [&](const Track::pointer& track) {
                    visitedTracks.push_back(track);
                },
                otherLibrary.getId());
            ASSERT_EQ(visitedTracks.size(), 0);
            EXPECT_EQ(lastRetrievedTrackId, TrackId{});
        }

        {
            auto transaction{ session.createReadTransaction() };

            TrackId lastRetrievedTrackId{};
            std::vector<Track::pointer> visitedTracks;
            Track::find(
                session, lastRetrievedTrackId, 10, [&](const Track::pointer& track) {
                    visitedTracks.push_back(track);
                },
                library.getId());
            ASSERT_EQ(visitedTracks.size(), 1);
            EXPECT_EQ(visitedTracks[0]->getId(), track2.getId());
            EXPECT_EQ(lastRetrievedTrackId, track2.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_findFilters)
    {
        ScopedUser user{ session, "testuser" };
        ScopedTrack track1{ session }; // 0 ms duration, no rating, NO MEDIUM
        ScopedTrack track2{ session }; // 5 min duration, rating 3
        ScopedTrack track3{ session }; // 15 min duration, rating 5

        {
            auto transaction{ session.createWriteTransaction() };
            track2.get().modify()->setDuration(std::chrono::minutes{ 5 });
            track3.get().modify()->setDuration(std::chrono::minutes{ 15 });

            // Set ratings manually
            auto rt2 = session.create<RatedTrack>(track2.get(), user.get());
            rt2.modify()->setRating(3);
            auto rt3 = session.create<RatedTrack>(track3.get(), user.get());
            rt3.modify()->setRating(5);
        }

        {
            auto transaction{ session.createReadTransaction() };

            // UI default: minRating=2, includeUnrated=true, maxDuration=10, sort=recent
            Track::FindParameters params;
            params.minRating = 2;
            params.includeUnrated = true;
            params.maxDuration = std::chrono::minutes{ 10 };
            params.ratingUser = user.getId();
            params.sortMethod = TrackSortMethod::OriginalDateDescAndRelease;

            auto results = Track::find(session, params);
            // Should find:
            // track1 (unrated, duration 0 <= 10, even with no medium!)
            // track2 (rated 3 >= 2, duration 5 <= 10)
            // NOT track3 (duration 15 > 10)
            ASSERT_EQ(results.results.size(), 2);
            EXPECT_EQ(results.results[0]->getId(), track1.getId());
            EXPECT_EQ(results.results[1]->getId(), track2.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_findNextIdRange)
    {
        {
            auto transaction{ session.createReadTransaction() };

            auto range{ Track::findNextIdRange(session, TrackId{}, 0) };
            EXPECT_FALSE(range.isValid());
            EXPECT_EQ(range.first, TrackId{});
            EXPECT_EQ(range.last, TrackId{});

            range = Track::findNextIdRange(session, TrackId{}, 100);
            EXPECT_FALSE(range.isValid());
            EXPECT_EQ(range.first, TrackId{});
            EXPECT_EQ(range.last, TrackId{});
        }

        ScopedTrack track1{ session };
        {
            auto transaction{ session.createReadTransaction() };

            auto range{ Track::findNextIdRange(session, TrackId{}, 0) };
            EXPECT_FALSE(range.isValid());
            EXPECT_EQ(range.first, TrackId{});
            EXPECT_EQ(range.last, TrackId{});

            range = Track::findNextIdRange(session, TrackId{}, 1);
            EXPECT_TRUE(range.isValid());
            EXPECT_EQ(range.first, track1.getId());
            EXPECT_EQ(range.last, track1.getId());

            range = Track::findNextIdRange(session, range.last, 1);
            EXPECT_FALSE(range.isValid());
            EXPECT_EQ(range.first, TrackId{});
            EXPECT_EQ(range.last, TrackId{});

            range = Track::findNextIdRange(session, TrackId{}, 100);
            EXPECT_TRUE(range.isValid());
            EXPECT_EQ(range.first, track1.getId());
            EXPECT_EQ(range.last, track1.getId());
        }

        ScopedTrack track2{ session };
        ScopedTrack track3{ session };

        {
            auto transaction{ session.createReadTransaction() };

            auto range{ Track::findNextIdRange(session, TrackId{}, 2) };
            EXPECT_TRUE(range.isValid());
            EXPECT_EQ(range.first, track1.getId());
            EXPECT_EQ(range.last, track2.getId());

            range = Track::findNextIdRange(session, track2.getId(), 2);
            EXPECT_TRUE(range.isValid());
            EXPECT_EQ(range.first, track3.getId());
            EXPECT_EQ(range.last, track3.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_findByRange)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };
        ScopedTrack track3{ session };

        {
            auto transaction{ session.createReadTransaction() };

            std::size_t count{};
            Track::find(session, IdRange<TrackId>{ .first = track1.getId(), .last = track1.getId() }, [&](const db::Track::pointer& track) {
                count++;
                EXPECT_EQ(track->getId(), track1.getId());
            });
            EXPECT_EQ(count, 1);
        }

        {
            auto transaction{ session.createReadTransaction() };

            std::size_t count{};
            Track::find(session, IdRange<TrackId>{ .first = track1.getId(), .last = track3.getId() }, [&](const db::Track::pointer&) {
                count++;
            });
            EXPECT_EQ(count, 3);
        }
    }

    TEST_F(DatabaseFixture, Track_findByCodec)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            track1.get().modify()->setCodec(core::media::Codec::MP3);
            track2.get().modify()->setCodec(core::media::Codec::FLAC);
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            params.setFilters(Filters{}.setCodec(core::media::Codec::FLAC));

            const auto tracks{ Track::find(session, params) };
            ASSERT_EQ(tracks.results.size(), 1);
            EXPECT_EQ(tracks.results[0]->getId(), track2.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_MediaLibrary)
    {
        ScopedTrack track{ session };
        ScopedMediaLibrary library{ session, "MyLibrary", "/root" };
        ScopedMediaLibrary otherLibrary{ session, "OtherLibrary", "/otherRoot" };

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_TRUE(library->isEmpty());
            EXPECT_TRUE(otherLibrary->isEmpty());
        }

        {
            auto transaction{ session.createWriteTransaction() };
            track.get().modify()->setMediaLibrary(library.get());
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_FALSE(library->isEmpty());
            EXPECT_TRUE(otherLibrary->isEmpty());
        }

        {
            auto transaction{ session.createReadTransaction() };
            const auto tracks{ Track::findIds(session, Track::FindParameters{}.setFilters(Filters{}.setMediaLibrary(library->getId()))) };
            ASSERT_EQ(tracks.results.size(), 1);
            EXPECT_EQ(tracks.results.front(), track.getId());
        }
        {
            auto transaction{ session.createReadTransaction() };
            const auto tracks{ Track::findIds(session, Track::FindParameters{}.setFilters(Filters{}.setMediaLibrary(otherLibrary->getId()))) };
            EXPECT_EQ(tracks.results.size(), 0);
        }
    }

    TEST_F(DatabaseFixture, Track_noMediaLibrary)
    {
        ScopedTrack track{ session };
        {
            auto transaction{ session.createReadTransaction() };
            MediaLibrary::pointer mediaLibrary{ track->getMediaLibrary() };
            EXPECT_EQ(mediaLibrary, MediaLibrary::pointer{});
            EXPECT_FALSE(mediaLibrary);
            EXPECT_TRUE(!mediaLibrary);
        }
    }

    TEST_F(DatabaseFixture, TrackNotExists)
    {
        auto transaction{ session.createReadTransaction() };

        EXPECT_FALSE(Track::exists(session, TrackId{ 42 }));
        EXPECT_EQ(Track::find(session, TrackId{ 42 }), Track::pointer{});
        EXPECT_FALSE(Track::find(session, TrackId{ 42 }));
        EXPECT_EQ(Track::find(session, Track::FindParameters{}).results.size(), 0);
        {
            auto track{ Track::find(session, TrackId{ 42 }) };
            EXPECT_TRUE(!track);
            EXPECT_FALSE(track);
        }
    }

    TEST_F(DatabaseFixture, MultipleTracks)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };

        {
            auto transaction{ session.createReadTransaction() };

            EXPECT_TRUE(track1.getId() != track2.getId());
            EXPECT_TRUE(track1.get() != track2.get());
            EXPECT_FALSE(track1.get() == track2.get());
        }
    }

    TEST_F(DatabaseFixture, MultipleTracksSearchByFilter)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };
        ScopedTrack track3{ session };
        ScopedTrack track4{ session };
        ScopedTrack track5{ session };
        ScopedTrack track6{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            track1.get().modify()->setName("MyTrack");
            track2.get().modify()->setName("MyTrack%");
            track3.get().modify()->setName("MyTrack%Foo");
            track4.get().modify()->setName("%MyTrack");
            track5.get().modify()->setName("Foo%MyTrack");
            track6.get().modify()->setName("M_Track");
        }

        {
            auto transaction{ session.createReadTransaction() };

            {
                const auto tracks{ Track::findIds(session, Track::FindParameters{}.setKeywords({ "Track" })) };
                EXPECT_EQ(tracks.results.size(), 6);
            }
            {
                const auto tracks{ Track::findIds(session, Track::FindParameters{}.setKeywords({ "MyTrack" })) };
                EXPECT_EQ(tracks.results.size(), 5);
                EXPECT_TRUE(std::none_of(std::cbegin(tracks.results), std::cend(tracks.results), [&](const TrackId trackId) { return trackId == track6.getId(); }));
            }
            {
                const auto tracks{ Track::findIds(session, Track::FindParameters{}.setKeywords({ "MyTrack%" })) };
                ASSERT_EQ(tracks.results.size(), 2);
                EXPECT_EQ(tracks.results[0], track2.getId());
                EXPECT_EQ(tracks.results[1], track3.getId());
            }
            {
                const auto tracks{ Track::findIds(session, Track::FindParameters{}.setKeywords({ "%MyTrack" })) };
                ASSERT_EQ(tracks.results.size(), 2);
                EXPECT_EQ(tracks.results[0], track4.getId());
                EXPECT_EQ(tracks.results[1], track5.getId());
            }
        }
    }

    TEST_F(DatabaseFixture, Track_date)
    {
        ScopedTrack track{ session };
        const core::PartialDateTime date{ 1995, 5, 5 };
        const core::PartialDateTime originalDate{ 1994, 2, 2 };
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getYear(), std::nullopt);
            EXPECT_EQ(track->getOriginalYear(), std::nullopt);
        }

        {
            auto transaction{ session.createWriteTransaction() };
            track.get().modify()->setDate(date);
            track.get().modify()->setOriginalDate(originalDate);
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getYear(), 1995);
            EXPECT_EQ(track->getOriginalYear(), 1994);
            EXPECT_EQ(track->getDate(), date);
            EXPECT_EQ(track->getOriginalDate(), originalDate);
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getYear(), date.getYear());
            EXPECT_EQ(track->getOriginalYear(), originalDate.getYear());
        }
    }

    TEST_F(DatabaseFixture, Track_writtenAfter)
    {
        ScopedTrack track{ session };

        const Wt::WDateTime dateTime{ Wt::WDate{ 1950, 1, 1 }, Wt::WTime{ 12, 30, 20 } };

        {
            auto transaction{ session.createWriteTransaction() };
            track.get().modify()->setLastWriteTime(dateTime);
        }

        {
            auto transaction{ session.createReadTransaction() };
            const auto tracks{ Track::findIds(session, Track::FindParameters{}) };
            EXPECT_EQ(tracks.results.size(), 1);
        }

        {
            auto transaction{ session.createReadTransaction() };
            const auto tracks{ Track::findIds(session, Track::FindParameters{}.setWrittenAfter(dateTime.addSecs(-1))) };
            EXPECT_EQ(tracks.results.size(), 1);
        }

        {
            auto transaction{ session.createReadTransaction() };
            const auto tracks{ Track::findIds(session, Track::FindParameters{}.setWrittenAfter(dateTime.addSecs(+1))) };
            EXPECT_EQ(tracks.results.size(), 0);
        }
    }

    TEST_F(DatabaseFixture, Track_path)
    {
        ScopedTrack track{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            track.get().modify()->setAbsoluteFilePath("/root/foo/file.path");
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getAbsoluteFilePath(), "/root/foo/file.path");
        }
    }

    namespace
    {
        // Every scoped-scan test needs the same thing: a track at a known absolute path.
        // ScopedEntity is neither copyable nor movable, so a factory function cannot hand one
        // back; the path is set by this wrapper's constructor instead.
        struct TrackAtPath
        {
            TrackAtPath(db::Session& session, const std::filesystem::path& path)
                : track{ session }
            {
                auto transaction{ session.createWriteTransaction() };
                track.get().modify()->setAbsoluteFilePath(path);
            }

            ScopedTrack track;
        };

        std::vector<std::filesystem::path> pathsUnder(db::Session& session, const std::filesystem::path& directory, std::size_t batchSize = 10)
        {
            auto transaction{ session.createReadTransaction() };
            std::vector<std::filesystem::path> found;
            TrackId lastRetrievedId;
            while (true)
            {
                const TrackId previous{ lastRetrievedId };
                Track::findAbsoluteFilePathInDirectory(session, lastRetrievedId, batchSize, directory, [&](TrackId, const std::filesystem::path& path) {
                    found.push_back(path);
                });
                if (previous == lastRetrievedId)
                    break;
            }
            return found;
        }
    } // namespace

    TEST_F(DatabaseFixture, Track_findAbsoluteFilePathInDirectory_returnsOnlyFilesUnderTheDirectory)
    {
        TrackAtPath inside{ session, "/music/A/1.mp3" };
        TrackAtPath deeper{ session, "/music/A/sub/2.mp3" };
        TrackAtPath elsewhere{ session, "/music/B/3.mp3" };

        EXPECT_EQ(pathsUnder(session, "/music/A"), (std::vector<std::filesystem::path>{ "/music/A/1.mp3", "/music/A/sub/2.mp3" }));
    }

    TEST_F(DatabaseFixture, Track_findAbsoluteFilePathInDirectory_doesNotMatchASiblingWithTheSameNamePrefix)
    {
        // The reason the bound is a range and not LIKE '/music/A%': that pattern pulls in
        // every release of a differently named label that happens to start the same way.
        TrackAtPath inside{ session, "/music/A/1.mp3" };
        TrackAtPath sibling{ session, "/music/AB/2.mp3" };

        EXPECT_EQ(pathsUnder(session, "/music/A"), (std::vector<std::filesystem::path>{ "/music/A/1.mp3" }));
    }

    TEST_F(DatabaseFixture, Track_findAbsoluteFilePathInDirectory_isCaseSensitive)
    {
        // SQLite's LIKE is case-insensitive for ASCII unless case_sensitive_like is set, so a
        // LIKE-based filter would return both of these on a case-sensitive filesystem.
        TrackAtPath upper{ session, "/music/A/1.mp3" };
        TrackAtPath lower{ session, "/music/a/2.mp3" };

        EXPECT_EQ(pathsUnder(session, "/music/A"), (std::vector<std::filesystem::path>{ "/music/A/1.mp3" }));
    }

    TEST_F(DatabaseFixture, Track_findAbsoluteFilePathInDirectory_toleratesATrailingSeparator)
    {
        TrackAtPath inside{ session, "/music/A/1.mp3" };

        EXPECT_EQ(pathsUnder(session, "/music/A/"), (std::vector<std::filesystem::path>{ "/music/A/1.mp3" }));
    }

    TEST_F(DatabaseFixture, Track_findAbsoluteFilePathInDirectory_paginatesWithoutRepeatingOrSkipping)
    {
        TrackAtPath one{ session, "/music/A/1.mp3" };
        TrackAtPath two{ session, "/music/A/2.mp3" };
        TrackAtPath three{ session, "/music/A/3.mp3" };
        TrackAtPath four{ session, "/music/A/4.mp3" };
        TrackAtPath five{ session, "/music/A/5.mp3" };

        const std::vector<std::filesystem::path> found{ pathsUnder(session, "/music/A", 2) };

        EXPECT_EQ(found.size(), 5);
        EXPECT_EQ(std::set<std::filesystem::path>(std::cbegin(found), std::cend(found)).size(), 5);
    }

    TEST_F(DatabaseFixture, Track_findAbsoluteFilePathInDirectory_stillReturnsRowsForADirectoryThatIsGone)
    {
        // The contract the whole scoped scan rests on: the query must not consult the
        // filesystem, or a folder that was moved away could never have its rows removed.
        TrackAtPath track{ session, "/music/vanished-4f1c/1.mp3" };

        EXPECT_EQ(pathsUnder(session, "/music/vanished-4f1c").size(), 1);
    }

    TEST_F(DatabaseFixture, Track_findAbsoluteFilePathInDirectory_returnsNothingForADirectoryWithNoFiles)
    {
        TrackAtPath elsewhere{ session, "/music/B/1.mp3" };

        EXPECT_TRUE(pathsUnder(session, "/music/A").empty());
    }

    TEST_F(DatabaseFixture, Track_audioProperties)
    {
        ScopedTrack track{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            track.get().modify()->setBitrate(128000);
            track.get().modify()->setBitsPerSample(16);
            track.get().modify()->setDuration(std::chrono::minutes{ 3 });
            track.get().modify()->setChannelCount(2);
            track.get().modify()->setSampleRate(44100);
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getBitrate(), 128000);
            EXPECT_EQ(track->getBitsPerSample(), 16);
            EXPECT_EQ(track->getDuration(), std::chrono::minutes{ 3 });
            EXPECT_EQ(track->getChannelCount(), 2);
            EXPECT_EQ(track->getSampleRate(), 44100);
        }
    }

    TEST_F(DatabaseFixture, Track_comment)
    {
        ScopedTrack track{ session };

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getComment(), "");
        }

        {
            auto transaction{ session.createWriteTransaction() };
            track.get().modify()->setComment("MyComment");
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getComment(), "MyComment");
        }
    }

    TEST_F(DatabaseFixture, Track_sortDateAdded)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };
        ScopedTrack track3{ session };
        ScopedTrack track4{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            track1.get().modify()->setAddedTime(Wt::WDateTime{ Wt::WDate{ 2021, 1, 2 } });
            track2.get().modify()->setAddedTime(Wt::WDateTime{ Wt::WDate{ 2021, 1, 1 } });
            track4.get().modify()->setAddedTime(Wt::WDateTime{ Wt::WDate{ 2021, 1, 2 }, Wt::WTime{ 15, 36, 24 } });
        }

        {
            auto transaction{ session.createReadTransaction() };
            const auto tracks{ Track::findIds(session, Track::FindParameters{}.setSortMethod(TrackSortMethod::AddedDesc)) };
            ASSERT_EQ(tracks.results.size(), 4);
            EXPECT_EQ(tracks.results[0], track4.getId());
            EXPECT_EQ(tracks.results[1], track1.getId());
            EXPECT_EQ(tracks.results[2], track2.getId());
            EXPECT_EQ(tracks.results[3], track3.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_sortLastWritten)
    {
        ScopedTrack track1{ session };
        ScopedTrack track2{ session };
        ScopedTrack track3{ session };
        ScopedTrack track4{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            track1.get().modify()->setLastWriteTime(Wt::WDateTime{ Wt::WDate{ 2021, 1, 2 } });
            track2.get().modify()->setLastWriteTime(Wt::WDateTime{ Wt::WDate{ 2021, 1, 1 } });
            track4.get().modify()->setLastWriteTime(Wt::WDateTime{ Wt::WDate{ 2021, 1, 2 }, Wt::WTime{ 15, 36, 24 } });
        }

        {
            auto transaction{ session.createReadTransaction() };
            const auto tracks{ Track::findIds(session, Track::FindParameters{}.setSortMethod(TrackSortMethod::LastWrittenDesc)) };
            ASSERT_EQ(tracks.results.size(), 4);
            EXPECT_EQ(tracks.results[0], track4.getId());
            EXPECT_EQ(tracks.results[1], track1.getId());
            EXPECT_EQ(tracks.results[2], track2.getId());
            EXPECT_EQ(tracks.results[3], track3.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_updateArtworks)
    {
        ScopedTrack track{ session };
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getPreferredArtwork(), Artwork::pointer{});
            EXPECT_EQ(track->getPreferredMediaArtwork(), Artwork::pointer{});
        }

        ScopedImage image1{ session, "/image1.jpg" };
        ScopedArtwork artwork1{ session, image1.lockAndGet() };
        ScopedImage image2{ session, "/image2.jpg" };
        ScopedArtwork artwork2{ session, image2.lockAndGet() };

        {
            auto transaction{ session.createWriteTransaction() };
            Track::updatePreferredArtwork(session, track->getId(), artwork1->getId());
            Track::updatePreferredMediaArtwork(session, track->getId(), artwork2->getId());
        }
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getPreferredArtwork()->getId(), artwork1->getId());
            EXPECT_EQ(track->getPreferredMediaArtwork()->getId(), artwork2->getId());
        }

        {
            auto transaction{ session.createWriteTransaction() };
            Track::updatePreferredArtwork(session, track->getId(), ArtworkId{});
            Track::updatePreferredMediaArtwork(session, track->getId(), ArtworkId{});
        }
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(track->getPreferredArtwork(), Artwork::pointer{});
            EXPECT_EQ(track->getPreferredMediaArtwork(), Artwork::pointer{});
        }
    }

    TEST_F(DatabaseFixture, Track_findAdvanced)
    {
        ScopedClusterType genreType{ session, "GENRE" };
        ScopedCluster rock{ session, genreType.lockAndGet(), "Rock" };
        ScopedCluster pop{ session, genreType.lockAndGet(), "Pop" };

        ScopedClusterType yearType{ session, "YEAR" };
        ScopedCluster y2020{ session, yearType.lockAndGet(), "2020" };
        ScopedCluster y2021{ session, yearType.lockAndGet(), "2021" };

        ScopedTrack trackRock2020{ session };
        ScopedTrack trackPop2021{ session };
        ScopedTrack trackRock2021{ session };

        ScopedUser user{ session, "user" };

        {
            auto transaction{ session.createWriteTransaction() };
            rock.get().modify()->addTrack(trackRock2020.get());
            y2020.get().modify()->addTrack(trackRock2020.get());
            trackRock2020.get().modify()->setDuration(std::chrono::minutes{ 5 });

            pop.get().modify()->addTrack(trackPop2021.get());
            y2021.get().modify()->addTrack(trackPop2021.get());
            trackPop2021.get().modify()->setDuration(std::chrono::minutes{ 3 });

            rock.get().modify()->addTrack(trackRock2021.get());
            y2021.get().modify()->addTrack(trackRock2021.get());
            trackRock2021.get().modify()->setDuration(std::chrono::minutes{ 15 });

            auto rt = session.create<RatedTrack>(trackRock2020.get(), user.get());
            rt.modify()->setRating(4);
        }

        {
            auto transaction{ session.createReadTransaction() };

            // Find by Genre AND Year
            {
                Track::FindParameters params;
                std::map<std::string, std::set<ClusterId>> clusterGroups;
                clusterGroups["GENRE"].insert(rock.getId());
                clusterGroups["YEAR"].insert(y2021.getId());

                std::vector<TrackId> foundIds;
                Track::find_advanced(session, params, clusterGroups, [&](const Track::pointer& t) {
                    foundIds.push_back(t->getId());
                });

                ASSERT_EQ(foundIds.size(), 1);
                EXPECT_EQ(foundIds[0], trackRock2021.getId());
            }

            // Find by Genre AND Max Duration
            {
                Track::FindParameters params;
                params.maxDuration = std::chrono::minutes{ 10 };
                std::map<std::string, std::set<ClusterId>> clusterGroups;
                clusterGroups["GENRE"].insert(rock.getId());

                std::vector<TrackId> foundIds;
                Track::find_advanced(session, params, clusterGroups, [&](const Track::pointer& t) {
                    foundIds.push_back(t->getId());
                });

                ASSERT_EQ(foundIds.size(), 1);
                EXPECT_EQ(foundIds[0], trackRock2020.getId());
            }

            // Find by Genre AND Min Rating
            {
                Track::FindParameters params;
                params.ratingUser = user.getId();
                params.minRating = 3;
                params.includeUnrated = false;
                std::map<std::string, std::set<ClusterId>> clusterGroups;
                clusterGroups["GENRE"].insert(rock.getId());

                std::vector<TrackId> foundIds;
                Track::find_advanced(session, params, clusterGroups, [&](const Track::pointer& t) {
                    foundIds.push_back(t->getId());
                });

                ASSERT_EQ(foundIds.size(), 1);
                EXPECT_EQ(foundIds[0], trackRock2020.getId());
            }

            // Find by Genre AND Min Rating (including unrated)
            {
                Track::FindParameters params;
                params.ratingUser = user.getId();
                params.minRating = 3;
                params.includeUnrated = true;
                std::map<std::string, std::set<ClusterId>> clusterGroups;
                clusterGroups["GENRE"].insert(rock.getId());

                std::vector<TrackId> foundIds;
                Track::find_advanced(session, params, clusterGroups, [&](const Track::pointer& t) {
                    foundIds.push_back(t->getId());
                });

                // Should find trackRock2020 (rated 4) and trackRock2021 (unrated)
                EXPECT_EQ(foundIds.size(), 2);
            }

            // Test sorting by rating
            {
                Track::FindParameters params;
                params.ratingUser = user.getId();
                params.sortMethod = TrackSortMethod::RatingDesc;

                std::vector<TrackId> foundIds;
                Track::find_advanced(session, params, {}, [&](const Track::pointer& t) {
                    foundIds.push_back(t->getId());
                });

                // trackRock2020 has rating 4, others have 0/NULL.
                // So trackRock2020 should be first.
                ASSERT_GT(foundIds.size(), 0);
                EXPECT_EQ(foundIds[0], trackRock2020.getId());
            }
        }
    }

    // The label view of the web UI browses through find_advanced, not through find:
    // a label that filters in one and not in the other shows the whole library.
    TEST_F(DatabaseFixture, Track_findAdvancedByLabel)
    {
        ScopedLabel label{ session, "Roughstate" };
        ScopedLabel otherLabel{ session, "Dirty Workz" };
        ScopedRelease release{ session, "Release" };
        ScopedRelease otherRelease{ session, "OtherRelease" };
        ScopedTrack onLabel{ session };
        ScopedTrack onOtherLabel{ session };
        ScopedTrack withoutRelease{ session };

        {
            auto transaction{ session.createWriteTransaction() };

            release.get().modify()->addLabel(label.get());
            otherRelease.get().modify()->addLabel(otherLabel.get());
            onLabel.get().modify()->setRelease(release.get());
            onOtherLabel.get().modify()->setRelease(otherRelease.get());
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            params.filters.setLabel(label.getId());

            std::vector<TrackId> foundIds;
            Track::find_advanced(session, params, {}, [&](const Track::pointer& t) {
                foundIds.push_back(t->getId());
            });

            ASSERT_EQ(foundIds.size(), 1);
            EXPECT_EQ(foundIds[0], onLabel.getId());

            // countAdvanced shares its query body with find_advanced, so a filter that
            // one honours and the other drops is exactly the drift this asserts against.
            EXPECT_EQ(Track::countAdvanced(session, params, {}), 1);
        }
    }

    // Form and filing year (docs/designs/track-form/) must mean the same in both query builders:
    // the web UI browses through find_advanced, radio and the older endpoints through find.
    namespace
    {
        struct FormFixtureTracks
        {
            TrackId liveset;
            TrackId set;
            TrackId track;
            TrackId unclassified;
        };

        // A live set played in 2012 but tagged 2016, a set and a track tagged 2012, and a track
        // muma never classified, also tagged 2012.
        void fillFormFixture(Session& session, ScopedTrack& liveset, ScopedTrack& set, ScopedTrack& track, ScopedTrack& unclassified)
        {
            auto transaction{ session.createWriteTransaction() };
            liveset.get().modify()->setForm("liveset");
            liveset.get().modify()->setPerformanceDate("2012-06-23");
            liveset.get().modify()->setDate(core::PartialDateTime{ 2016, 1, 1 });
            set.get().modify()->setForm("set");
            set.get().modify()->setDate(core::PartialDateTime{ 2012, 12, 31 });
            track.get().modify()->setForm("track");
            track.get().modify()->setDate(core::PartialDateTime{ 2012, 3, 1 });
            unclassified.get().modify()->setDate(core::PartialDateTime{ 2012, 5, 5 });
        }

        std::vector<TrackId> findAdvancedIds(Session& session, const Track::FindParameters& params)
        {
            std::vector<TrackId> ids;
            Track::find_advanced(session, params, {}, [&](const Track::pointer& t) { ids.push_back(t->getId()); });
            std::sort(ids.begin(), ids.end());
            return ids;
        }

        std::vector<TrackId> findTrackIds(Session& session, const Track::FindParameters& params)
        {
            const auto results{ Track::findIds(session, params) };
            std::vector<TrackId> ids{ results.results.begin(), results.results.end() };
            std::sort(ids.begin(), ids.end());
            return ids;
        }

        std::vector<TrackId> sorted(std::vector<TrackId> ids)
        {
            std::sort(ids.begin(), ids.end());
            return ids;
        }
    } // namespace

    TEST_F(DatabaseFixture, Track_findByForm_bothBuilders)
    {
        ScopedTrack liveset{ session };
        ScopedTrack set{ session };
        ScopedTrack track{ session };
        ScopedTrack unclassified{ session };
        fillFormFixture(session, liveset, set, track, unclassified);

        auto transaction{ session.createReadTransaction() };

        Track::FindParameters params;
        params.forms = { "liveset" };
        EXPECT_EQ(findAdvancedIds(session, params), std::vector<TrackId>{ liveset.getId() });
        EXPECT_EQ(findTrackIds(session, params), std::vector<TrackId>{ liveset.getId() });
        EXPECT_EQ(Track::countAdvanced(session, params, {}), 1);

        // Several forms are OR; a track muma never classified matches none of them.
        params.forms = { "liveset", "set" };
        EXPECT_EQ(findAdvancedIds(session, params), sorted({ liveset.getId(), set.getId() }));
        EXPECT_EQ(findTrackIds(session, params), sorted({ liveset.getId(), set.getId() }));
    }

    TEST_F(DatabaseFixture, Track_excludesNonMusic_bothBuilders)
    {
        ScopedTrack song{ session };
        ScopedTrack interview{ session };
        ScopedTrack preview{ session };
        ScopedTrack unclassified{ session };
        {
            auto transaction{ session.createWriteTransaction() };
            song.get().modify()->setForm("track");
            interview.get().modify()->setForm("interview");
            preview.get().modify()->setForm("preview");
        }

        auto transaction{ session.createReadTransaction() };

        // Off by default: every caller that does not ask keeps seeing every track.
        Track::FindParameters params;
        const std::vector<TrackId> everything{ sorted({ song.getId(), interview.getId(), preview.getId(), unclassified.getId() }) };
        EXPECT_EQ(findAdvancedIds(session, params), everything);
        EXPECT_EQ(findTrackIds(session, params), everything);

        // Asked for: the non-music forms go, an unclassified track stays.
        params.excludeNonMusic = true;
        const std::vector<TrackId> music{ sorted({ song.getId(), unclassified.getId() }) };
        EXPECT_EQ(findAdvancedIds(session, params), music);
        EXPECT_EQ(findTrackIds(session, params), music);
        EXPECT_EQ(Track::countAdvanced(session, params, {}), 2);

        // Naming a non-music form lists it, exclusion or not.
        params.forms = { "interview" };
        EXPECT_EQ(findAdvancedIds(session, params), std::vector<TrackId>{ interview.getId() });
        EXPECT_EQ(findTrackIds(session, params), std::vector<TrackId>{ interview.getId() });

        // A music form keeps the exclusion, and needs it for nothing.
        params.forms = { "track" };
        EXPECT_EQ(findTrackIds(session, params), std::vector<TrackId>{ song.getId() });
    }

    TEST_F(DatabaseFixture, Track_findByFilingYear_bothBuilders)
    {
        ScopedTrack liveset{ session };
        ScopedTrack set{ session };
        ScopedTrack track{ session };
        ScopedTrack unclassified{ session };
        fillFormFixture(session, liveset, set, track, unclassified);

        auto transaction{ session.createReadTransaction() };

        // The live set files under the year it was played, not the 2016 on its tag.
        Track::FindParameters params;
        params.year = 2012;
        const std::vector<TrackId> in2012{ sorted({ liveset.getId(), set.getId(), track.getId(), unclassified.getId() }) };
        EXPECT_EQ(findAdvancedIds(session, params), in2012);
        EXPECT_EQ(findTrackIds(session, params), in2012);

        params.year = 2016;
        EXPECT_TRUE(findAdvancedIds(session, params).empty());
        EXPECT_TRUE(findTrackIds(session, params).empty());

        // Combined: live sets from 2012.
        params.year = 2012;
        params.forms = { "liveset" };
        EXPECT_EQ(findAdvancedIds(session, params), std::vector<TrackId>{ liveset.getId() });
        EXPECT_EQ(Track::countAdvanced(session, params, {}), 1);
    }

    TEST_F(DatabaseFixture, Track_getCountByArtist)
    {
        ScopedArtist artistA{ session, "artistA" };
        ScopedArtist artistB{ session, "artistB" };
        ScopedTrack trackA1{ session };
        ScopedTrack trackA2{ session };
        ScopedTrack trackB1{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            session.create<TrackArtistLink>(trackA1.get(), artistA.get(), TrackArtistLinkType::Artist);
            session.create<TrackArtistLink>(trackA2.get(), artistA.get(), TrackArtistLinkType::Artist);
            session.create<TrackArtistLink>(trackB1.get(), artistB.get(), TrackArtistLinkType::Artist);
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(Track::getCount(session, Track::FindParameters{}.setArtist(artistA.getId())), 2);
            EXPECT_EQ(Track::getCount(session, Track::FindParameters{}.setArtist(artistB.getId())), 1);
            EXPECT_EQ(Track::getCount(session, Track::FindParameters{}), 3);
        }
    }

    TEST_F(DatabaseFixture, Track_findAdvanced_byArtists)
    {
        ScopedArtist headhunterz{ session, "Headhunterz" };
        ScopedArtist wildstylez{ session, "Wildstylez" };

        ScopedTrack solo{ session };
        ScopedTrack collab{ session };
        ScopedTrack otherSolo{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            session.create<TrackArtistLink>(solo.get(), headhunterz.get(), TrackArtistLinkType::Artist);
            session.create<TrackArtistLink>(collab.get(), headhunterz.get(), TrackArtistLinkType::Artist);
            session.create<TrackArtistLink>(collab.get(), wildstylez.get(), TrackArtistLinkType::Artist);
            session.create<TrackArtistLink>(otherSolo.get(), wildstylez.get(), TrackArtistLinkType::Artist);
        }

        auto findIds{ [&](const std::set<ArtistId>& artists) {
            Track::FindParameters params;
            params.setArtists(artists, { TrackArtistLinkType::Artist });

            std::vector<TrackId> foundIds;
            Track::find_advanced(session, params, {}, [&](const Track::pointer& t) {
                foundIds.push_back(t->getId());
            });
            return foundIds;
        } };

        {
            auto transaction{ session.createReadTransaction() };

            // One artist: everything they are on, collaborations included.
            {
                const auto foundIds{ findIds({ headhunterz.getId() }) };
                ASSERT_EQ(foundIds.size(), 2);
                EXPECT_NE(std::find(foundIds.begin(), foundIds.end(), collab.getId()), foundIds.end());
            }

            // Two artists: only what they made together.
            {
                const auto foundIds{ findIds({ headhunterz.getId(), wildstylez.getId() }) };
                ASSERT_EQ(foundIds.size(), 1);
                EXPECT_EQ(foundIds[0], collab.getId());
            }

            // An artist nobody worked with matches nothing rather than everything.
            {
                ScopedArtist stranger{ session, "Stranger" };
                const auto foundIds{ findIds({ headhunterz.getId(), stranger.getId() }) };
                EXPECT_TRUE(foundIds.empty());
            }
        }
    }

    TEST_F(DatabaseFixture, Track_findAdvanced_byArtistsAndGenre)
    {
        ScopedClusterType genreType{ session, "GENRE" };
        ScopedCluster hardstyle{ session, genreType.lockAndGet(), "Hardstyle" };

        ScopedArtist headhunterz{ session, "Headhunterz" };
        ScopedArtist wildstylez{ session, "Wildstylez" };

        ScopedTrack hardstyleCollab{ session };
        ScopedTrack untaggedCollab{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            for (auto* track : { &hardstyleCollab, &untaggedCollab })
            {
                session.create<TrackArtistLink>(track->get(), headhunterz.get(), TrackArtistLinkType::Artist);
                session.create<TrackArtistLink>(track->get(), wildstylez.get(), TrackArtistLinkType::Artist);
            }
            hardstyle.get().modify()->addTrack(hardstyleCollab.get());
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            params.setArtists({ headhunterz.getId(), wildstylez.getId() }, { TrackArtistLinkType::Artist });

            std::map<std::string, std::set<ClusterId>> clusterGroups;
            clusterGroups["GENRE"].insert(hardstyle.getId());

            std::vector<TrackId> foundIds;
            Track::find_advanced(session, params, clusterGroups, [&](const Track::pointer& t) {
                foundIds.push_back(t->getId());
            });

            ASSERT_EQ(foundIds.size(), 1);
            EXPECT_EQ(foundIds[0], hardstyleCollab.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_findAdvanced_byFestival)
    {
        ScopedClusterType festivalType{ session, "FESTIVAL" };
        ScopedCluster defqon{ session, festivalType.lockAndGet(), "Defqon.1 2025" };

        ScopedTrack atFestival{ session };
        // Deliberately left untagged: it is the track that must not come back, and without
        // it the assertion below would pass against an empty library.
        ScopedTrack elsewhere{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            defqon.get().modify()->addTrack(atFestival.get());
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;

            std::map<std::string, std::set<ClusterId>> clusterGroups;
            clusterGroups["FESTIVAL"].insert(defqon.getId());

            std::vector<TrackId> foundIds;
            Track::find_advanced(session, params, clusterGroups, [&](const Track::pointer& t) {
                foundIds.push_back(t->getId());
            });

            ASSERT_EQ(foundIds.size(), 1);
            EXPECT_EQ(foundIds[0], atFestival.getId());
        }
    }

    TEST_F(DatabaseFixture, Track_findAdvanced_byAllowedArtistNames)
    {
        ScopedTrack solo{ session };
        ScopedTrack collab{ session };
        ScopedTrack other{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            solo.get().modify()->setArtistDisplayName("Angerfist");
            collab.get().modify()->setArtistDisplayName("Angerfist & Outsiders");
            other.get().modify()->setArtistDisplayName("Wildstylez");
        }

        auto findIds{ [&](const std::set<std::string>& artists) {
            Track::FindParameters params;
            params.setAllowedArtists(artists);

            std::vector<TrackId> foundIds;
            Track::find_advanced(session, params, {}, [&](const Track::pointer& t) {
                foundIds.push_back(t->getId());
            });
            return foundIds;
        } };

        {
            auto transaction{ session.createReadTransaction() };

            // The match is on the whole display name, case-insensitively.
            {
                const auto foundIds{ findIds({ "angerfist" }) };
                ASSERT_EQ(foundIds.size(), 1);
                EXPECT_EQ(foundIds[0], solo.getId());
            }

            // A collaboration is a different display name and is therefore NOT matched by
            // one of its members. This is the behaviour a lineup page inherits, and the
            // reason a lineup can look thinner than the festival page beside it.
            {
                const auto foundIds{ findIds({ "angerfist", "wildstylez" }) };
                ASSERT_EQ(foundIds.size(), 2);
                EXPECT_EQ(std::find(foundIds.begin(), foundIds.end(), collab.getId()), foundIds.end());
            }

            // An empty allowed set is "no restriction", not "match nothing".
            {
                EXPECT_EQ(findIds({}).size(), 3);
            }
        }
    }

    TEST_F(DatabaseFixture, Track_findAdvanced_byArtistAndMismatchedArtistName)
    {
        // setArtist (singular) + setArtistName must keep meaning "the artist with this id also
        // has this name" -- i.e. the SAME link row -- even though setArtists (plural) now gives
        // each wanted artist its own alias. A collaboration track must not satisfy "id = A" and
        // "name = B" just because A and B are both linked to it via different rows.
        ScopedArtist headhunterz{ session, "Headhunterz" };
        ScopedArtist wildstylez{ session, "Wildstylez" };

        ScopedTrack collab{ session };
        ScopedTrack soloA{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            session.create<TrackArtistLink>(collab.get(), headhunterz.get(), TrackArtistLinkType::Artist);
            session.create<TrackArtistLink>(collab.get(), wildstylez.get(), TrackArtistLinkType::Artist);
            session.create<TrackArtistLink>(soloA.get(), headhunterz.get(), TrackArtistLinkType::Artist);
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::FindParameters params;
            // setArtistName overwrites trackArtistLinkTypes, so set it last to keep the filter.
            params.setArtist(headhunterz.getId()).setArtistName("Wildstylez", { TrackArtistLinkType::Artist });

            std::vector<TrackId> foundIds;
            Track::find_advanced(session, params, {}, [&](const Track::pointer& t) {
                foundIds.push_back(t->getId());
            });

            // Neither track has a single link row that is both "Headhunterz" and "Wildstylez",
            // so nothing should match -- not even the collaboration track.
            EXPECT_TRUE(foundIds.empty());
        }
    }

    TEST_F(DatabaseFixture, Track_countAdvanced)
    {
        ScopedClusterType genreType{ session, "GENRE" };
        ScopedCluster hardstyle{ session, genreType.lockAndGet(), "Hardstyle" };

        ScopedTrack tagged1{ session };
        ScopedTrack tagged2{ session };
        ScopedTrack untagged{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            hardstyle.get().modify()->addTrack(tagged1.get());
            hardstyle.get().modify()->addTrack(tagged2.get());
        }

        {
            auto transaction{ session.createReadTransaction() };

            std::map<std::string, std::set<ClusterId>> clusterGroups;
            clusterGroups["GENRE"].insert(hardstyle.getId());

            // The count ignores the range: it answers "how many are there", not "how many did
            // this page return".
            Track::FindParameters params;
            params.setRange(Range{ 0, 1 });

            std::vector<TrackId> firstPage;
            Track::find_advanced(session, params, clusterGroups, [&](const Track::pointer& t) {
                firstPage.push_back(t->getId());
            });

            EXPECT_EQ(firstPage.size(), 1);
            EXPECT_EQ(Track::countAdvanced(session, params, clusterGroups), 2);
            EXPECT_EQ(Track::countAdvanced(session, Track::FindParameters{}, {}), 3);
        }
    }

    TEST_F(DatabaseFixture, Track_findIdsByReleaseAnniversary)
    {
        ScopedTrack exactMatch{ session };
        ScopedTrack windowMatch{ session };
        ScopedTrack yearOnly{ session };
        ScopedTrack yearAndMonthOnly{ session };
        ScopedTrack thisYear{ session };
        ScopedTrack otherDay{ session };

        {
            auto transaction{ session.createWriteTransaction() };

            exactMatch.get().modify()->setOriginalDate(core::PartialDateTime{ 2018, 8, 2 });
            windowMatch.get().modify()->setOriginalDate(core::PartialDateTime{ 2015, 8, 4 });
            // Neither of these can establish an anniversary: no day in the tag.
            yearOnly.get().modify()->setOriginalDate(core::PartialDateTime{ 2016 });
            yearAndMonthOnly.get().modify()->setOriginalDate(core::PartialDateTime{ 2014, 8 });
            thisYear.get().modify()->setOriginalDate(core::PartialDateTime{ 2026, 8, 2 });
            otherDay.get().modify()->setOriginalDate(core::PartialDateTime{ 2017, 8, 20 });
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::ReleaseAnniversaryParameters params;
            params.month = 8;
            params.day = 2;
            params.windowDays = 3;
            params.currentYear = 2026;

            const auto results{ Track::findIdsByReleaseAnniversary(session, params) };

            // Newest year first: 2018 before 2015.
            EXPECT_EQ(results.results, (std::vector<TrackId>{ exactMatch.getId(), windowMatch.getId() }));
        }
    }

    TEST_F(DatabaseFixture, Track_findIdsByReleaseAnniversary_fallsBackToDate)
    {
        ScopedTrack fallback{ session };
        ScopedTrack prefersOriginal{ session };

        {
            auto transaction{ session.createWriteTransaction() };

            // No original date at all: the plain date is what a memory is built from.
            fallback.get().modify()->setDate(core::PartialDateTime{ 2019, 8, 2 });

            // Both set: the original release is the memory, not the reissue.
            prefersOriginal.get().modify()->setDate(core::PartialDateTime{ 2021, 12, 25 });
            prefersOriginal.get().modify()->setOriginalDate(core::PartialDateTime{ 2011, 8, 2 });
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::ReleaseAnniversaryParameters params;
            params.month = 8;
            params.day = 2;
            params.windowDays = 0;
            params.currentYear = 2026;

            const auto results{ Track::findIdsByReleaseAnniversary(session, params) };

            EXPECT_EQ(results.results, (std::vector<TrackId>{ fallback.getId(), prefersOriginal.getId() }));
        }
    }

    TEST_F(DatabaseFixture, Track_findIdsByReleaseAnniversary_wrapsAroundNewYear)
    {
        ScopedTrack december{ session };
        ScopedTrack january{ session };

        {
            auto transaction{ session.createWriteTransaction() };

            december.get().modify()->setOriginalDate(core::PartialDateTime{ 2014, 12, 30 });
            january.get().modify()->setOriginalDate(core::PartialDateTime{ 2012, 1, 3 });
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::ReleaseAnniversaryParameters params;
            params.month = 1;
            params.day = 1;
            params.windowDays = 3;
            params.currentYear = 2026;

            const auto results{ Track::findIdsByReleaseAnniversary(session, params) };

            EXPECT_EQ(results.results, (std::vector<TrackId>{ december.getId(), january.getId() }));
        }
    }

    TEST_F(DatabaseFixture, Track_findIdsByReleaseAnniversary_includesLeapDay)
    {
        ScopedTrack leapDay{ session };

        {
            auto transaction{ session.createWriteTransaction() };
            leapDay.get().modify()->setOriginalDate(core::PartialDateTime{ 2020, 2, 29 });
        }

        {
            auto transaction{ session.createReadTransaction() };

            Track::ReleaseAnniversaryParameters params;
            params.month = 2;
            params.day = 28;
            params.windowDays = 3;
            params.currentYear = 2026;

            const auto results{ Track::findIdsByReleaseAnniversary(session, params) };

            EXPECT_EQ(results.results, (std::vector<TrackId>{ leapDay.getId() }));
        }
    }

    // getSpotifyTracks sort=recent orders by COALESCE(original_date, date): with the expression
    // index SQLite walks the index and stops after the page; without it every page was a full
    // scan of track plus a sort (0.65 s per query on a copy of production's 343,000 tracks). The
    // ORDER BY below is sortMethodToSQL(OriginalDateDescAndRelease) verbatim -- SQLite only uses
    // an expression index for the identical expression.
    TEST_F(DatabaseFixture, Track_originalDateSortWalksItsIndex)
    {
        auto transaction{ session.createReadTransaction() };

        Wt::Dbo::Transaction dboTransaction{ *session.getDboSession() };
        auto statement{ dboTransaction.connection()->prepareStatement("EXPLAIN QUERY PLAN SELECT DISTINCT t.id FROM track t LEFT JOIN medium m ON t.medium_id = m.id"
                                                                      " ORDER BY COALESCE(t.original_date, t.date) DESC, t.release_id, m.position, t.track_number LIMIT 201") };
        statement->execute();

        std::string plan;
        while (statement->nextRow())
        {
            std::string detail;
            detail.reserve(256);
            if (statement->getResult(3, &detail, static_cast<int>(detail.capacity())))
                plan += detail + '\n';
        }

        EXPECT_NE(plan.find("track_filing_date_release_idx"), std::string::npos) << plan;
    }
} // namespace lms::db::tests
