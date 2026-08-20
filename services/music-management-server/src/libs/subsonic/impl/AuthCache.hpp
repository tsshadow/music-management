/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <chrono>
#include <cstddef>
#include <optional>
#include <string>
#include <unordered_map>

#include "database/objects/UserId.hpp"

namespace lms::api::subsonic
{
    // Remembers how an incoming set of credentials was answered, so a repeat of the same
    // credentials does not have to reach the database again.
    //
    // Caching *failures* is the part that matters. AuthTokenService resolves an API key through the
    // database, and a client stuck on a stale key -- muma-radio after an LMS restart, say -- keeps
    // retrying several times a minute forever. Answering those from memory keeps them off the
    // database entirely, on top of the read-first fix in AuthTokenService::processAuthToken.
    //
    // Because an unauthenticated caller can therefore put entries in here, the map is explicitly
    // bounded: see the eviction rules on store().
    class AuthCache
    {
    public:
        struct Entry
        {
            db::UserId userId; // only meaningful when granted
            bool granted{};
        };

        AuthCache(std::chrono::seconds grantedDuration, std::chrono::seconds deniedDuration, std::size_t maxEntryCount);

        // Returns nothing when the key is unknown or its entry has lapsed.
        std::optional<Entry> lookup(const std::string& key, std::chrono::steady_clock::time_point now) const;

        void storeGranted(const std::string& key, db::UserId userId, std::chrono::steady_clock::time_point now);
        void storeDenied(const std::string& key, std::chrono::steady_clock::time_point now);

        std::size_t getEntryCount() const { return _entries.size(); }

    private:
        struct StoredEntry
        {
            db::UserId userId;
            bool granted{};
            std::chrono::steady_clock::time_point expiry;
        };

        void store(const std::string& key, StoredEntry entry, std::chrono::steady_clock::time_point now);
        void removeExpired(std::chrono::steady_clock::time_point now);
        // Gives up a denial before a grant, and otherwise whichever entry lapses first. Returns
        // false only when there was nothing at all to evict.
        bool evictOne();

        const std::chrono::seconds _grantedDuration;
        const std::chrono::seconds _deniedDuration;
        const std::size_t _maxEntryCount;

        std::unordered_map<std::string, StoredEntry> _entries;
    };
} // namespace lms::api::subsonic
