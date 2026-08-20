/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "AuthCache.hpp"

#include <algorithm>

namespace lms::api::subsonic
{
    AuthCache::AuthCache(std::chrono::seconds grantedDuration, std::chrono::seconds deniedDuration, std::size_t maxEntryCount)
        : _grantedDuration{ grantedDuration }
        , _deniedDuration{ deniedDuration }
        , _maxEntryCount{ maxEntryCount }
    {
    }

    std::optional<AuthCache::Entry> AuthCache::lookup(const std::string& key, std::chrono::steady_clock::time_point now) const
    {
        const auto it{ _entries.find(key) };
        if (it == std::cend(_entries))
            return std::nullopt;

        if (it->second.expiry <= now)
            return std::nullopt;

        return Entry{ .userId = it->second.userId, .granted = it->second.granted };
    }

    void AuthCache::storeGranted(const std::string& key, db::UserId userId, std::chrono::steady_clock::time_point now)
    {
        store(key, StoredEntry{ .userId = userId, .granted = true, .expiry = now + _grantedDuration }, now);
    }

    void AuthCache::storeDenied(const std::string& key, std::chrono::steady_clock::time_point now)
    {
        store(key, StoredEntry{ .userId = {}, .granted = false, .expiry = now + _deniedDuration }, now);
    }

    void AuthCache::store(const std::string& key, StoredEntry entry, std::chrono::steady_clock::time_point now)
    {
        // Refreshing what is already here can never grow the map, so it needs no room made for it.
        if (const auto it{ _entries.find(key) }; it != std::end(_entries))
        {
            it->second = entry;
            return;
        }

        if (_entries.size() >= _maxEntryCount)
            removeExpired(now);

        if (_entries.size() >= _maxEntryCount)
        {
            // Still full of live entries. A grant is worth making room for: the caller proved who
            // they are, and sending them back to the database on every request is the load this
            // cache exists to avoid. A denial is not -- dropping it only means the next bad request
            // from that client is resolved the slow way, which is what an unbounded map would cost
            // us anyway.
            if (!entry.granted || !evictOne())
                return;
        }

        _entries.emplace(key, entry);
    }

    void AuthCache::removeExpired(std::chrono::steady_clock::time_point now)
    {
        std::erase_if(_entries, [now](const auto& entry) { return entry.second.expiry <= now; });
    }

    bool AuthCache::evictOne()
    {
        // Give up a denial before a grant, and otherwise the entry that was going to lapse first.
        auto victim{ std::end(_entries) };

        for (auto it{ std::begin(_entries) }; it != std::end(_entries); ++it)
        {
            if (victim == std::end(_entries))
            {
                victim = it;
                continue;
            }

            if (victim->second.granted && !it->second.granted)
                victim = it;
            else if (victim->second.granted == it->second.granted && it->second.expiry < victim->second.expiry)
                victim = it;
        }

        if (victim == std::end(_entries))
            return false;

        _entries.erase(victim);
        return true;
    }
} // namespace lms::api::subsonic
