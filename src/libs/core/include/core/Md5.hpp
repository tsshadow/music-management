#pragma once

#include <string>
#include <string_view>

namespace lms::core::crypto
{
    [[nodiscard]] std::string md5(std::string_view data);
} // namespace lms::core::crypto
