#pragma once

#include <set>
#include <string>

class FestivalLineupRepository
{
public:
    static std::set<std::string> getArtistsForFestival(const std::string& festival);
    static std::set<std::string> getAllLineups();
};
