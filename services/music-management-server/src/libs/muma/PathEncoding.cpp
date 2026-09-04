#include "api/muma/PathEncoding.hpp"

#include <cctype>

namespace lms::api::muma
{
    namespace
    {
        bool isUnreserved(unsigned char c)
        {
            // RFC 3986 unreserved, plus '/' because the separators of the path being rebuilt
            // must survive. Everything else is encoded, including '%' itself: the input is
            // already decoded, so a percent in it belongs to the name.
            return std::isalnum(c) || c == '-' || c == '.' || c == '_' || c == '~' || c == '/';
        }
    } // namespace

    std::string encodeProxyPath(std::string_view decodedPath)
    {
        static constexpr char hexDigits[]{ "0123456789ABCDEF" };

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
                encoded += hexDigits[c >> 4];
                encoded += hexDigits[c & 0x0F];
            }
        }

        return encoded;
    }
} // namespace lms::api::muma
