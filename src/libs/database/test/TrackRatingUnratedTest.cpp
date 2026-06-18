
#include "Common.hpp"
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"

namespace lms::db::tests
{
    TEST_F(DatabaseFixture, TrackRatingUnrated)
    {
        ScopedUser user{ session, "testuser" };
        
        // Create 3 tracks
        ScopedTrack trackUnrated{ session }; // No rating
        ScopedTrack track1Star{ session };   // 1 star
        ScopedTrack track2Stars{ session };  // 2 stars
        ScopedTrack track0Star{ session };   // 0 stars (specifically set)

        {
            auto transaction{ session.createWriteTransaction() };
            
            // Set ratings in the track table (global)
            track1Star.get().modify()->persist(transaction); // ensure persisted
            utils::executeCommand(*session.getDboSession(), "UPDATE track SET rating = 1 WHERE id = ?", track1Star.getId());
            
            track2Stars.get().modify()->persist(transaction);
            utils::executeCommand(*session.getDboSession(), "UPDATE track SET rating = 2 WHERE id = ?", track2Stars.getId());

            track0Star.get().modify()->persist(transaction);
            utils::executeCommand(*session.getDboSession(), "UPDATE track SET rating = 0 WHERE id = ?", track0Star.getId());
        }

        {
            auto transaction{ session.createReadTransaction() };
            
            Track::FindParameters params;
            params.minRating = 2;
            params.includeUnrated = true;
            
            auto results = Track::findIds(session, params).results;
            
            // We expect: trackUnrated (NULL), track2Stars (2), track0Star (0)
            // We do NOT expect: track1Star (1)
            
            EXPECT_EQ(results.size(), 3);
            EXPECT_NE(std::find(results.begin(), results.end(), trackUnrated.getId()), results.end());
            EXPECT_NE(std::find(results.begin(), results.end(), track2Stars.getId()), results.end());
            EXPECT_NE(std::find(results.begin(), results.end(), track0Star.getId()), results.end());
            EXPECT_EQ(std::find(results.begin(), results.end(), track1Star.getId()), results.end());
        }
        
        // Test with per-user rating
        {
            auto transaction{ session.createWriteTransaction() };
            // Rate tracks for our user
            utils::executeCommand(*session.getDboSession(), "INSERT INTO rated_track (track_id, user_id, rating) VALUES (?, ?, 1)", track1Star.getId(), user.getId());
            utils::executeCommand(*session.getDboSession(), "INSERT INTO rated_track (track_id, user_id, rating) VALUES (?, ?, 2)", track2Stars.getId(), user.getId());
            utils::executeCommand(*session.getDboSession(), "INSERT INTO rated_track (track_id, user_id, rating) VALUES (?, ?, 0)", track0Star.getId(), user.getId());
        }
        
        {
            auto transaction{ session.createReadTransaction() };
            
            Track::FindParameters params;
            params.minRating = 2;
            params.includeUnrated = true;
            params.ratingUser = user.getId();
            
            auto results = Track::findIds(session, params).results;
            
            EXPECT_EQ(results.size(), 3);
            EXPECT_NE(std::find(results.begin(), results.end(), trackUnrated.getId()), results.end());
            EXPECT_NE(std::find(results.begin(), results.end(), track2Stars.getId()), results.end());
            EXPECT_NE(std::find(results.begin(), results.end(), track0Star.getId()), results.end());
            EXPECT_EQ(std::find(results.begin(), results.end(), track1Star.getId()), results.end());
        }
    }
}
