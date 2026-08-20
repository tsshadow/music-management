/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#pragma once

#include <atomic>
#include <cstddef>

namespace lms::core
{
    // Caps how many callers may be inside a slow section at once, and turns the rest away instead
    // of queueing them.
    //
    // Refusing is the point. The callers here are Wt resource handlers, and each one owns an HTTP
    // server thread for as long as it runs -- there are only as many of those as the machine has
    // cores. Handlers that waited on music-management could therefore take the whole pool between
    // them, after which the server answered nothing at all, an unauthenticated ping included, until
    // it was restarted. A caller that is turned away can degrade gracefully in a few microseconds;
    // one that waits its turn is holding the very thing that ran out.
    class ConcurrencyGate
    {
    public:
        // A limit of 0 is treated as 1: a caller computing this from a thread count should never
        // accidentally wedge the gate shut.
        explicit ConcurrencyGate(std::size_t maxConcurrent);

        class Lease
        {
        public:
            ~Lease();

            Lease(Lease&& other) noexcept;
            Lease(const Lease&) = delete;
            Lease& operator=(const Lease&) = delete;
            Lease& operator=(Lease&&) = delete;

            // False when the gate was full and nothing was reserved.
            explicit operator bool() const { return _gate != nullptr; }

        private:
            friend class ConcurrencyGate;
            explicit Lease(ConcurrencyGate* gate)
                : _gate{ gate } {}

            ConcurrencyGate* _gate;
        };

        [[nodiscard]] Lease tryAcquire();

        std::size_t getInUseCount() const { return _inUseCount.load(); }
        std::size_t getMaxConcurrent() const { return _maxConcurrent; }

    private:
        void release();

        const std::size_t _maxConcurrent;
        std::atomic<std::size_t> _inUseCount{};
    };
} // namespace lms::core
