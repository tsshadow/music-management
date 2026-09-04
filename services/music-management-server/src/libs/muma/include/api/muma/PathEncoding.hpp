#pragma once

#include <string>
#include <string_view>

namespace lms::api::muma
{
    /// Percent-encode a decoded request path so it can be put back on the wire.
    ///
    /// Wt hands `Wt::Http::Request::pathInfo()` over already decoded, so an artist called
    /// "Silky Noize" arrives here with a real space in it. Forwarding that verbatim puts a
    /// space in the request line and MuMa answers 400 before the route is ever matched.
    /// Only the path is encoded: `/` stays a separator, and the query string is a separate
    /// argument that is still encoded and must not be touched.
    std::string encodeProxyPath(std::string_view decodedPath);
} // namespace lms::api::muma
