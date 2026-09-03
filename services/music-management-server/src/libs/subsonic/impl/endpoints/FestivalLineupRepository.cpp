#include "FestivalLineupRepository.hpp"

#include <fstream>
#include <optional>
#include <string>
#include <system_error>

namespace fs = std::filesystem;

namespace
{
    // A `const fs::path` here would be a static that constructs -- and can throw -- before main;
    // the path is built where it is used instead.
    constexpr const char* lineupRoot{ "/music/metadata/festival-lineups" };

    // The lineup id arrives as a client parameter (`festivalLineup=`, `lineup=`) and is turned
    // into a path, so it is resolved and then checked to still sit under the root: "../../../etc"
    // is a perfectly ordinary id as far as the caller is concerned.
    std::optional<fs::path> resolveWithinRoot(const fs::path& root, const std::string& lineup)
    {
        if (lineup.empty())
        {
            return std::nullopt;
        }

        std::error_code ec;
        const fs::path canonicalRoot{ fs::weakly_canonical(root, ec) };
        if (ec)
        {
            return std::nullopt;
        }

        fs::path candidate{ fs::weakly_canonical(canonicalRoot / lineup, ec) };
        if (ec)
        {
            return std::nullopt;
        }

        const fs::path relative{ candidate.lexically_relative(canonicalRoot) };
        if (relative.empty() || relative.begin()->string() == "..")
        {
            return std::nullopt;
        }

        return candidate;
    }

    void readArtists(const fs::path& file, std::set<std::string>& artists)
    {
        std::ifstream stream{ file };
        if (!stream.is_open())
        {
            return;
        }

        std::string line;
        while (std::getline(stream, line))
        {
            // Trim whitespace
            line.erase(0, line.find_first_not_of(" \t\r\n"));
            line.erase(line.find_last_not_of(" \t\r\n") + 1);

            if (!line.empty())
            {
                artists.insert(line);
            }
        }
    }

    bool isLineupFile(const fs::directory_entry& entry)
    {
        return entry.is_regular_file() && entry.path().extension() == ".txt";
    }
} // namespace

std::set<std::string> FestivalLineupRepository::getArtistsForFestival(const std::string& festival)
{
    return getArtistsForFestival(lineupRoot, festival);
}

std::set<std::string> FestivalLineupRepository::getArtistsForFestival(const fs::path& root, const std::string& festival)
{
    std::set<std::string> artists;

    const std::optional<fs::path> resolved{ resolveWithinRoot(root, festival) };
    if (!resolved)
    {
        return artists; // an id that points outside the lineup directory names no artists
    }

    fs::path file{ *resolved };
    file += ".txt";
    readArtists(file, artists);

    // A directory of the same name is the union of every lineup below it: the stages of an
    // edition, the editions of a festival. Both may exist, and then both are read.
    std::error_code ec;
    if (fs::is_directory(*resolved, ec))
    {
        for (const auto& entry : fs::recursive_directory_iterator(*resolved, ec))
        {
            if (isLineupFile(entry))
            {
                readArtists(entry.path(), artists);
            }
        }
    }

    return artists;
}

std::set<std::string> FestivalLineupRepository::getAllLineups()
{
    return getAllLineups(lineupRoot);
}

std::set<std::string> FestivalLineupRepository::getAllLineups(const fs::path& root)
{
    std::set<std::string> result;

    std::error_code ec;
    if (!fs::is_directory(root, ec))
    {
        return result;
    }

    for (const auto& entry : fs::recursive_directory_iterator(root, ec))
    {
        if (!isLineupFile(entry))
        {
            continue;
        }

        // e.g. Defqon.1/2014/RED, and with it the two lineups it rolls up into. The separator is
        // '/' on every platform because the id travels over the API, not over the filesystem.
        fs::path relative{ fs::relative(entry.path(), root, ec).replace_extension() };
        for (; !relative.empty() && relative != relative.parent_path(); relative = relative.parent_path())
        {
            result.insert(relative.generic_string());
        }
    }

    return result;
}
