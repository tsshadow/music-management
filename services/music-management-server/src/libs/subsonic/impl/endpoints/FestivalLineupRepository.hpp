#pragma once

#include <filesystem>
#include <set>
#include <string>

// A lineup lives in /music/metadata/festival-lineups as a text file of artist names, and its id is
// the path to that file without the extension: "Intents 2025", but also "Defqon.1/2014/RED". Every
// directory on such a path is a lineup in its own right, holding the union of everything below it,
// so "Defqon.1/2014" is that edition across its stages and "Defqon.1" is the festival across its
// editions -- without a single artist name being written down twice.
class FestivalLineupRepository
{
public:
    static std::set<std::string> getArtistsForFestival(const std::string& festival);
    static std::set<std::string> getAllLineups();

    // The same, against an explicit root. Only the tests pass one; everything else reads the
    // deployed directory.
    static std::set<std::string> getArtistsForFestival(const std::filesystem::path& root, const std::string& festival);
    static std::set<std::string> getAllLineups(const std::filesystem::path& root);
};
