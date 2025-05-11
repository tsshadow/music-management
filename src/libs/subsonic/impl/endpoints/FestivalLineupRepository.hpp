#pragma once

#include <string>
#include <set>

class FestivalLineupRepository
{
public:
  static std::set<std::string> getArtistsForFestival(const std::string& festival) ;

};
