/*
 * Copyright (C) 2026 Teun Schriks
 *
 * This file is part of LMS.
 */

#include "core/ConcurrencyGate.hpp"

#include <algorithm>

namespace lms::core
{
    ConcurrencyGate::ConcurrencyGate(std::size_t maxConcurrent)
        : _maxConcurrent{ std::max<std::size_t>(1, maxConcurrent) }
    {
    }

    ConcurrencyGate::Lease::~Lease()
    {
        if (_gate)
            _gate->release();
    }

    ConcurrencyGate::Lease::Lease(Lease&& other) noexcept
        : _gate{ other._gate }
    {
        other._gate = nullptr;
    }

    ConcurrencyGate::Lease ConcurrencyGate::tryAcquire()
    {
        std::size_t current{ _inUseCount.load(std::memory_order_relaxed) };

        while (current < _maxConcurrent)
        {
            if (_inUseCount.compare_exchange_weak(current, current + 1, std::memory_order_acquire, std::memory_order_relaxed))
                return Lease{ this };
        }

        return Lease{ nullptr };
    }

    void ConcurrencyGate::release()
    {
        _inUseCount.fetch_sub(1, std::memory_order_release);
    }
} // namespace lms::core
