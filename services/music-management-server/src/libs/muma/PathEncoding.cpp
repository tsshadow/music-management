#include "api/muma/PathEncoding.hpp"

#include <cctype>

namespace lms::api::muma
{
    namespace
    {
        constexpr unsigned char decimalDigitCount{ 10 };
        constexpr unsigned char lowNibbleMask{ 0x0F };
        constexpr unsigned int nibbleBitCount{ 4 };

        bool isUnreserved(unsigned char c)
        {
            // RFC 3986 unreserved, plus '/' because the separators of the path being rebuilt
            // must survive. Everything else is encoded, including '%' itself: the input is
            // already decoded, so a percent in it belongs to the name.
            return std::isalnum(c) || c == '-' || c == '.' || c == '_' || c == '~' || c == '/';
        }

        char toHexDigit(unsigned char nibble)
        {
            return static_cast<char>(nibble < decimalDigitCount ? '0' + nibble : 'A' + (nibble - decimalDigitCount));
        }
    } // namespace

    std::string encodeProxyPath(std::string_view decodedPath)
    {
        std::string encoded;
        encoded.reserve(decodedPath.size());

        for (const char rawChar : decodedPath)
        {
            const unsigned char c{ static_cast<unsigned char>(rawChar) };
            if (isUnreserved(c))
            {
                encoded += rawChar;
            }
            else
            {
                encoded += '%';
                encoded += toHexDigit(c >> nibbleBitCount);
                encoded += toHexDigit(c & lowNibbleMask);
            }
        }

        return encoded;
    }
} // namespace lms::api::muma
