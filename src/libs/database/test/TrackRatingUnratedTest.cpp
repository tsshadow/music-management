
#include "Common.hpp"
#include <Wt/Dbo/Call.h>
#include "database/objects/Track.hpp"
#include "database/objects/User.hpp"
#include "database/objects/RatedTrack.hpp"

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
            track1Star.get().modify()->setRating(1);
            track2Stars.get().modify()->setRating(2);
            track0Star.get().modify()->setRating(0);
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
            session.create<RatedTrack>(track1Star.get(), user.get()).modify()->setRating(1);
            session.create<RatedTrack>(track2Stars.get(), user.get()).modify()->setRating(2);
            session.create<RatedTrack>(track0Star.get(), user.get()).modify()->setRating(0);
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
