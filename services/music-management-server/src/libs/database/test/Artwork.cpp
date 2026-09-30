/*
 * Copyright (C) 2025of LMS.
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

#include <Wt/Dbo/Dbo.h>

#include "Common.hpp"

#include "database/objects/Artwork.hpp"
#include "database/objects/Image.hpp"
#include "database/objects/TrackEmbeddedImage.hpp"
#include "database/objects/TrackEmbeddedImageLink.hpp"

namespace lms::db::tests
{
    using ScopedArtwork = ScopedEntity<db::Artwork>;
    using ScopedImage = ScopedEntity<db::Image>;
    using ScopedTrackEmbeddedImage = ScopedEntity<db::TrackEmbeddedImage>;

    // Removing an image removes its artwork, and SQLite then sets every column that references
    // that artwork to NULL. Each of those columns needs an index whose first column it is, or every
    // single removal scans the table: 0.2 s a row on production, 20,000 portrait rows each library
    // scan (bug report 138). Checked on the columns themselves rather than by index name, so a
    // renamed index still passes and a dropped one does not; and after dropping them, because an
    // existing database gets them from the next start, not from a migration step.
    TEST_F(DatabaseFixture, Artwork_everyReferenceToAnArtworkIsIndexed)
    {
        const std::vector<std::pair<std::string, std::string>> references{
            { "artist", "preferred_artwork_id" },
            { "medium", "preferred_artwork_id" },
            { "podcast", "artwork_id" },
            { "podcast_episode", "artwork_id" },
            { "release", "preferred_artwork_id" },
            { "track", "preferred_artwork_id" },
            { "track", "preferred_media_artwork_id" },
            { "artwork", "image_id" },
            { "artwork", "track_embedded_image_id" },
        };

        const auto leadingIndexCount{ [&](const std::string& table, const std::string& column) {
            auto transaction{ session.createReadTransaction() };
            return session.getDboSession()->query<int>("SELECT COUNT(*) FROM pragma_index_list(?) il JOIN pragma_index_info(il.name) ii WHERE ii.seqno = 0 AND ii.name = ?").bind(table).bind(column).resultValue();
        } };

        for (const auto& [table, column] : references)
            EXPECT_GE(leadingIndexCount(table, column), 1) << table << "." << column;

        {
            auto transaction{ session.createWriteTransaction() };
            for (const auto& [table, column] : references)
            {
                // Only the ones this change added; the artwork ones predate it and stay.
                if (table != "artwork")
                    session.execute("DROP INDEX IF EXISTS " + table + "_" + column.substr(0, column.size() - 3) + "_idx");
            }
        }
        EXPECT_EQ(leadingIndexCount("track", "preferred_artwork_id"), 0) << "the drop above should have removed it";

        session.createIndexesIfNeeded();
        for (const auto& [table, column] : references)
            EXPECT_GE(leadingIndexCount(table, column), 1) << table << "." << column << " after a restart";
    }

    TEST_F(DatabaseFixture, Artwork_image)
    {
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(Artwork::getCount(session), 0);
        }

        ScopedImage image{ session, "/MyImage" };
        ScopedArtwork artwork{ session, image.lockAndGet() };

        const Wt::WDateTime dateTime{ Wt::WDate{ 2025, 1, 1 } };

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(Artwork::getCount(session), 1);
        }

        {
            auto transaction{ session.createWriteTransaction() };
            image.get().modify()->setLastWriteTime(dateTime);
            image.get().modify()->setAbsoluteFilePath("/tmp/foo");
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(artwork.get()->getLastWrittenTime(), dateTime);
            EXPECT_EQ(artwork.get()->getAbsoluteFilePath(), "/tmp/foo");
        }
    }

    TEST_F(DatabaseFixture, Artwork_trackEmbeddedImage)
    {
        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(Artwork::getCount(session), 0);
        }

        ScopedTrackEmbeddedImage image{ session };
        ScopedTrack track{ session };
        ScopedArtwork artwork{ session, image.lockAndGet() };

        const Wt::WDateTime dateTime{ Wt::WDate{ 2025, 1, 1 } };

        {
            auto transaction{ session.createWriteTransaction() };
            session.create<db::TrackEmbeddedImageLink>(track.get(), image.get());
            track.get().modify()->setLastWriteTime(dateTime);
            track.get().modify()->setAbsoluteFilePath("/tmp/foo");
        }

        {
            auto transaction{ session.createReadTransaction() };
            EXPECT_EQ(artwork.get()->getLastWrittenTime(), dateTime);
            EXPECT_EQ(artwork.get()->getAbsoluteFilePath(), "/tmp/foo");
        }
    }

    TEST_F(DatabaseFixture, Artwork_underlyingId)
    {
        ScopedImage image1{ session, "/MyImage" };
        ScopedArtwork artwork1{ session, image1.lockAndGet() };

        ScopedTrackEmbeddedImage image2{ session };
        ScopedArtwork artwork2{ session, image2.lockAndGet() };

        {
            auto transaction{ session.createReadTransaction() };
            const auto underlyingId{ artwork1.get()->getUnderlyingId() };
            ASSERT_TRUE(std::holds_alternative<db::ImageId>(underlyingId));
            EXPECT_EQ(std::get<db::ImageId>(underlyingId), image1.getId());
        }

        {
            auto transaction{ session.createReadTransaction() };
            const auto underlyingId{ artwork2.get()->getUnderlyingId() };
            ASSERT_TRUE(std::holds_alternative<db::TrackEmbeddedImageId>(underlyingId));
            EXPECT_EQ(std::get<db::TrackEmbeddedImageId>(underlyingId), image2.getId());
        }
    }
} // namespace lms::db::tests
