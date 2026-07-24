#include "FestivalLineupRepository.hpp"

#include <filesystem>
#include <fstream>
#include <sstream>

namespace fs = std::filesystem;

std::set<std::string> FestivalLineupRepository::getArtistsForFestival(const std::string& festival)
{
    std::set<std::string> artists;

    const std::string filePath = "/music/metadata/festival-lineups/" + festival + ".txt";
    std::ifstream file(filePath);

    if (!file.is_open())
    {
        return artists; // return empty if file not found
    }

    std::string line;
    while (std::getline(file, line))
    {
        // Trim whitespace
        line.erase(0, line.find_first_not_of(" \t\r\n"));
        line.erase(line.find_last_not_of(" \t\r\n") + 1);

        if (!line.empty())
        {
            artists.insert(line);
        }
    }

    return artists;
}

std::set<std::string> FestivalLineupRepository::getAllLineups()
{
    std::set<std::string> result;

    const std::string directory = "/music/metadata/festival-lineups";

    if (!fs::exists(directory) || !fs::is_directory(directory))
    {
        return result;
    }

    for (const auto& entry : fs::directory_iterator(directory))
    {
        if (entry.is_regular_file())
        {
            if (const auto& path = entry.path(); path.extension() == ".txt")
            {
                result.insert(path.stem().string()); // e.g. intents_2025
            }
        }
    }

    return result;
}
