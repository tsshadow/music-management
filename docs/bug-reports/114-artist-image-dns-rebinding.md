# title: The artist image URL check leaves a DNS-rebinding window

# status: fixed

# reported problem
GitLab issue #37, the gap left open by [bug report 037](037-management-routes-open-to-every-user.md).
"Set image from URL" (`POST /api/artists/{id}/image/url`) resolved the URL's host, refused it when
any address was not globally routable, and then downloaded it with `requests.get`. `requests`
resolves the name again. A DNS server that answers with a public address to the check and with
`127.0.0.1`, `192.0.2.27`, a Docker bridge address or `169.254.169.254` to the fetch (DNS
rebinding, a TTL of 0 is enough) turned the check into a formality: the download reached an
internal service with the curator's request (server-side request forgery). The same applied to
every redirect hop, each checked and then fetched with a fresh lookup.

The bulk fetcher had no check at all: `ImageDownloader.download` fetched whatever image URL a
provider's API answer (Spotify, Last.fm, SoundCloud) contained, with no address check and no size
cap.

# Possible reason
The check and the connection were two separate name lookups. Any scheme that validates a name and
then hands the URL to an HTTP client that resolves on its own has this window; it can only be
closed by connecting to the very address that was checked.

# solution
New module `services/music_manager/artist_image_fetcher/safe_fetch.py`, used by both the route
(`download_public_image`) and the bulk fetcher (`ImageDownloader`):

- Each host is resolved exactly once (`resolve_public`). Every address it returns must be public;
  one internal address among public ones refuses the URL. "Internal" is an explicit list on top of
  `ipaddress.is_global`: `0.0.0.0/8`, `10/8`, CGNAT `100.64/10` (the tailnet), `127/8`,
  `169.254/16` (metadata), `172.16/12` (Docker bridges), `192.168/16`, the documentation and
  benchmark ranges, multicast and reserved space, and for IPv6 `::`, `::1`, `fc00::/7`,
  `fe80::/10`, `fec0::/10`, `ff00::/8`, `2001:db8::/32`. An IPv6 address that embeds an IPv4 one
  (IPv4-mapped, IPv4-compatible, 6to4, Teredo, NAT64) is refused when the embedded address is.
- The connection goes to the checked address: a urllib3 connection pool bound to the IP, with the
  original name as the `Host` header, as the TLS SNI (`server_hostname`) and as the name the
  certificate is verified against (`assert_hostname`, CA bundle from certifi). No second lookup of
  the name happens anywhere. Environment proxies are not used, since a proxy would resolve again.
- Redirects are followed by hand (301/302/303/307/308), each hop split, resolved and checked the
  same way; a non-http(s) target or more than three redirects is refused.
- The body is read with `read1` so a server dripping bytes still hits the checks: cut off at
  10 MB (413 on the route), and the whole exchange -- all hops plus body -- bounded by the
  10-second deadline, on top of the per-read socket timeout.
- `ImageDownloader` does not retry a refused URL or an oversized body; it still retries network
  errors with backoff.

Tests: `services/music_manager/artist_image_fetcher/tests/test_safe_fetch.py` (a resolver answering
public then private is asked once and the connection goes to the public address; a redirect or a
rebinding answer on the redirect to a private address is refused before connecting; IPv6,
IPv4-mapped, 6to4, NAT64 and CGNAT are refused; an end-to-end fetch from a real loopback server
reachable only through the pinned address carries the original `Host`; the deadline cuts off a
drip, a stall times out, the size cap holds), plus the route cases in
`services/music_manager/tests/test_rbac_route_gaps.py` and the retry cases in `test_storage.py`.
