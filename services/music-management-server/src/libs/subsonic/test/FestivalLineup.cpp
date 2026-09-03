/*
 * copyright (c) 2026 emeric poupon
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

#include <filesystem>
#include <fstream>

#include <gtest/gtest.h>

#include "endpoints/FestivalLineupRepository.hpp"

namespace fs = std::filesystem;

namespace lms::api::subsonic::tests
{
    class FestivalLineup : public ::testing::Test
    {
    protected:
        void SetUp() override
        {
            const std::string name{ ::testing::UnitTest::GetInstance()->current_test_info()->name() };
            _root = fs::temp_directory_path() / "festival-lineups-test" / name;
            _outside = fs::temp_directory_path() / "festival-lineups-test" / (name + "-outside");
            fs::remove_all(_root);
            fs::remove_all(_outside);
            fs::create_directories(_root);
            fs::create_directories(_outside);
        }

        void TearDown() override
        {
            fs::remove_all(_root);
            fs::remove_all(_outside);
        }

        void writeLineup(const std::string& relativePath, const std::string& contents)
        {
            const fs::path file{ _root / relativePath };
            fs::create_directories(file.parent_path());
            std::ofstream{ file } << contents;
        }

        fs::path _root;
        fs::path _outside;
    };

    TEST_F(FestivalLineup, readsAFlatLineupFile)
    {
        writeLineup("Intents 2025.txt", "Angerfist\n\n  Sub Zero Project  \n");

        const std::set<std::string> artists{ FestivalLineupRepository::getArtistsForFestival(_root, "Intents 2025") };

        EXPECT_EQ(artists, (std::set<std::string>{ "Angerfist", "Sub Zero Project" }));
    }

    TEST_F(FestivalLineup, readsOneStageOfAnEdition)
    {
        writeLineup("Defqon.1/2014/RED.txt", "Angerfist\n");
        writeLineup("Defqon.1/2014/BLUE.txt", "Da Tweekaz\n");

        const std::set<std::string> artists{ FestivalLineupRepository::getArtistsForFestival(_root, "Defqon.1/2014/RED") };

        EXPECT_EQ(artists, (std::set<std::string>{ "Angerfist" }));
    }

    TEST_F(FestivalLineup, aDirectoryIsTheUnionOfEverythingBelowIt)
    {
        writeLineup("Defqon.1/2014/RED.txt", "Angerfist\nDa Tweekaz\n");
        writeLineup("Defqon.1/2014/BLUE.txt", "Da Tweekaz\n");
        writeLineup("Defqon.1/2025/RED.txt", "Sub Zero Project\n");

        EXPECT_EQ(FestivalLineupRepository::getArtistsForFestival(_root, "Defqon.1/2014"),
                  (std::set<std::string>{ "Angerfist", "Da Tweekaz" }));
        EXPECT_EQ(FestivalLineupRepository::getArtistsForFestival(_root, "Defqon.1"),
                  (std::set<std::string>{ "Angerfist", "Da Tweekaz", "Sub Zero Project" }));
    }

    TEST_F(FestivalLineup, aFileAndADirectoryOfTheSameNameAreBothRead)
    {
        writeLineup("Dominator.txt", "Angerfist\n");
        writeLineup("Dominator/2026.txt", "Da Tweekaz\n");

        EXPECT_EQ(FestivalLineupRepository::getArtistsForFestival(_root, "Dominator"),
                  (std::set<std::string>{ "Angerfist", "Da Tweekaz" }));
    }

    TEST_F(FestivalLineup, listsEveryStageAndTheLineupsItRollsUpInto)
    {
        writeLineup("Defqon.1/2014/RED.txt", "Angerfist\n");
        writeLineup("Harmony of Hardcore 2026.txt", "Angerfist\n");

        const std::set<std::string> lineups{ FestivalLineupRepository::getAllLineups(_root) };

        EXPECT_EQ(lineups,
                  (std::set<std::string>{ "Defqon.1", "Defqon.1/2014", "Defqon.1/2014/RED", "Harmony of Hardcore 2026" }));
    }

    TEST_F(FestivalLineup, ignoresFilesThatAreNotLineups)
    {
        writeLineup("Defqon.1/2014/cover.jpg", "not a lineup");

        EXPECT_TRUE(FestivalLineupRepository::getAllLineups(_root).empty());
    }

    TEST_F(FestivalLineup, aMissingLineupNamesNoArtists)
    {
        EXPECT_TRUE(FestivalLineupRepository::getArtistsForFestival(_root, "Defqon.1/2099").empty());
        EXPECT_TRUE(FestivalLineupRepository::getArtistsForFestival(_root, "").empty());
    }

    TEST_F(FestivalLineup, refusesAnIdThatLeavesTheLineupDirectory)
    {
        // The id is a client parameter, and it used to be pasted straight into a path.
        std::ofstream{ _outside / "secrets.txt" } << "Angerfist\n";
        const fs::path relativeEscape{ fs::path{ ".." } / _outside.filename() / "secrets" };

        EXPECT_TRUE(FestivalLineupRepository::getArtistsForFestival(_root, relativeEscape.string()).empty());
        EXPECT_TRUE(FestivalLineupRepository::getArtistsForFestival(_root, (_outside / "secrets").string()).empty());
    }

    TEST_F(FestivalLineup, aMissingLineupDirectoryListsNothing)
    {
        EXPECT_TRUE(FestivalLineupRepository::getAllLineups(_root / "nope").empty());
    }
} // namespace lms::api::subsonic::tests
