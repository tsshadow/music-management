#!/bin/bash
# scripts/test/reverse-proxy-routing.sh
# Proves which upstream the frontend reverse proxy hands each /muma path to,
# and that the path reaches it intact.
#
# The real nginx image runs the real reverse-proxy.conf against two stub
# upstreams named "lms" and "music-manager" that answer every request with
# what they received: the raw request line and the X-API-Key header. Every
# case below is a routing decision that matters in production and that no
# other test exercises -- the e2e stacks talk to LMS and MuMa directly and
# never go through this config. Getting one of them wrong looks fine locally
# and breaks login, artist images or the library admin on prod.
#
# Usage: ./scripts/test/reverse-proxy-routing.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONF="$ROOT_DIR/services/music-management-server/nginx/reverse-proxy.conf"
TAG="${CI_JOB_ID:-$$}"
NET="muma-proxy-test-$TAG"
STUB_DIR="$(mktemp -d)"

cleanup() {
    docker rm -f "lms-stub-$TAG" "muma-stub-$TAG" "proxy-stub-$TAG" >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
    rm -rf "$STUB_DIR"
}
trap cleanup EXIT

cat > "$STUB_DIR/stub.py" <<'PY'
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

NAME = sys.argv[1]
PORT = int(sys.argv[2])

class Echo(BaseHTTPRequestHandler):
    def _answer(self):
        body = json.dumps({
            "upstream": NAME,
            "method": self.command,
            "path": self.path,
            "x_api_key": self.headers.get("X-API-Key"),
            "x_forwarded_for": self.headers.get("X-Forwarded-For"),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _answer
    def log_message(self, *args):
        pass

HTTPServer(("0.0.0.0", PORT), Echo).serve_forever()
PY

docker network create "$NET" >/dev/null
docker run -d --rm --name "lms-stub-$TAG" --network "$NET" --network-alias lms \
    -v "$STUB_DIR/stub.py:/stub.py:ro" python:3-alpine python /stub.py lms 5082 >/dev/null
docker run -d --rm --name "muma-stub-$TAG" --network "$NET" --network-alias music-manager \
    -v "$STUB_DIR/stub.py:/stub.py:ro" python:3-alpine python /stub.py music-manager 8000 >/dev/null
docker run -d --rm --name "proxy-stub-$TAG" --network "$NET" --network-alias proxy \
    -v "$CONF:/etc/nginx/conf.d/default.conf:ro" nginx:alpine >/dev/null

# The client runs inside the lms stub: busybox wget cannot send a PUT or a
# DELETE, and python can. Raw path in, raw response out.
cat > "$STUB_DIR/ask.py" <<'PY'
import http.client, sys
# http.client sends the path verbatim; urllib would re-quote it and hide
# exactly the double-encoding this test is here to catch.
method, path = sys.argv[1], sys.argv[2]
headers = {"X-API-Key": "k1"}
# Optional third argument: the X-Forwarded-For an outer proxy would send.
if len(sys.argv) > 3:
    headers["X-Forwarded-For"] = sys.argv[3]
try:
    conn = http.client.HTTPConnection("proxy", 80, timeout=5)
    conn.request(method, path, headers=headers)
    print(conn.getresponse().read().decode())
except Exception as e:
    print("ERROR", e)
PY
docker cp "$STUB_DIR/ask.py" "lms-stub-$TAG:/ask.py"

# nginx refuses to start on a config error; say so instead of timing out below.
for _ in $(seq 1 30); do
    if docker exec "lms-stub-$TAG" python /ask.py GET /muma/api/config 2>/dev/null | grep -q upstream; then break; fi
    if ! docker ps -q --filter "name=proxy-stub-$TAG" | grep -q .; then
        echo "nginx did not start:"; docker logs "proxy-stub-$TAG" 2>&1 | tail -5; exit 1
    fi
    sleep 0.5
done

failures=0
# expect <method> <request path> <upstream> <path as the upstream saw it>
expect() {
    local method="$1" path="$2" want_upstream="$3" want_path="$4"
    local got
    got=$(docker exec "lms-stub-$TAG" python /ask.py "$method" "$path" 2>&1 || true)
    local upstream seen_path key
    upstream=$(printf '%s' "$got" | sed -n 's/.*"upstream": "\([^"]*\)".*/\1/p')
    seen_path=$(printf '%s' "$got" | sed -n 's/.*"path": "\([^"]*\)".*/\1/p')
    key=$(printf '%s' "$got" | sed -n 's/.*"x_api_key": "\([^"]*\)".*/\1/p')
    if [ "$upstream" = "$want_upstream" ] && [ "$seen_path" = "$want_path" ] && [ "$key" = "k1" ]; then
        echo "ok    $method $path -> $upstream $seen_path"
    else
        echo "FAIL  $method $path -> got upstream='$upstream' path='$seen_path' key='$key'; want $want_upstream $want_path"
        failures=$((failures + 1))
    fi
}

# Ordinary MuMa calls: straight to MuMa, /muma stripped, query intact, the path
# encoded exactly once (a space stays "%20"; an encoded slash becomes a slash,
# which is what uvicorn would have made of it anyway).
expect GET    "/muma/api/auth/verify"                                   music-manager "/api/auth/verify"
expect GET    "/muma/api/library/genres"                                music-manager "/api/library/genres"
expect GET    "/muma/api/feeds/daily-mix-soft?limit=10"                 music-manager "/api/feeds/daily-mix-soft?limit=10"
expect GET    "/muma/api/curation/artists/AC%2FDC"                      music-manager "/api/curation/artists/AC/DC"
expect GET    "/muma/api/curation/labels/Q-dance%20Records?x=1&y=a%20b" music-manager "/api/curation/labels/Q-dance%20Records?x=1&y=a%20b"
expect GET    "/muma/api/curation/artists/D%C3%A9j%C3%A0%20Vu"          music-manager "/api/curation/artists/D%C3%A9j%C3%A0%20Vu"
expect POST   "/muma/api/users/1/settings/frontend"                     music-manager "/api/users/1/settings/frontend"
expect PATCH  "/muma/api/users/1/settings/frontend"                     music-manager "/api/users/1/settings/frontend"
expect PUT    "/muma/api/radio/channels/3"                              music-manager "/api/radio/channels/3"
expect DELETE "/muma/api/radio/channels/3"                              music-manager "/api/radio/channels/3"
expect GET    "/muma/api/news/bulletins/2026-09-17.mp3"                 music-manager "/api/news/bulletins/2026-09-17.mp3"
expect GET    "/muma/api/artists/search?q=x"                            music-manager "/api/artists/search?q=x"
expect GET    "/muma/api/artists/images/stats"                          music-manager "/api/artists/images/stats"
expect POST   "/muma/api/artists/12/fetch-image"                        music-manager "/api/artists/12/fetch-image"
expect GET    "/muma/api/tracks/12/versions"                            music-manager "/api/tracks/12/versions"
expect GET    "/muma/api/admin-ish/thing"                               music-manager "/api/admin-ish/thing"
# The login goes to MuMa, which answers with the user's own key. LMS used to
# answer it itself, with its own api-key for everybody.
expect POST   "/muma/api/auth/login"                                    music-manager "/api/auth/login"

# LMS-owned routes: the ones MumaResource implements itself, path untouched.
expect GET    "/muma/api/admin/libraries?u=user&p=x"                    lms "/muma/api/admin/libraries?u=user&p=x"
expect DELETE "/muma/api/admin/libraries/4?u=user&p=x"                  lms "/muma/api/admin/libraries/4?u=user&p=x"
expect GET    "/muma/api/admin/subsonic-token?u=user&username=bob"      lms "/muma/api/admin/subsonic-token?u=user&username=bob"
expect GET    "/muma/api/artists/Angerfist/image?u=user&p=x"            lms "/muma/api/artists/Angerfist/image?u=user&p=x"
expect GET    "/muma/api/artists/Silky%20Noize/image?u=user"            lms "/muma/api/artists/Silky%20Noize/image?u=user"
expect GET    "/muma/api/artists/123"                                   lms "/muma/api/artists/123"
expect GET    "/muma/api/artists/angerfist-123"                         lms "/muma/api/artists/angerfist-123"
expect POST   "/muma/api/tracks/42/refresh?u=user&p=x"                  lms "/muma/api/tracks/42/refresh?u=user&p=x"
expect GET    "/muma/users/sync"                                        lms "/muma/users/sync"
expect GET    "/muma/users/settings/frontend?u=user&p=x"                lms "/muma/users/settings/frontend?u=user&p=x"

# The two namespaces that were never MuMa's.
expect GET    "/rest/ping.view?u=user"                                  lms "/rest/ping.view?u=user"
expect GET    "/index.html"                                             lms "/spotify/index.html"

# expect_forwarded_for <X-Forwarded-For sent> <X-Forwarded-For MuMa must see>
# The test client sits on a Docker bridge, a trusted private network, so it
# plays the part of Nginx Proxy Manager: whatever the browser sent comes first,
# the address NPM saw is appended last. MuMa's login rate limit keys on the
# left-most entry, so it must receive the right-most untrusted address alone --
# never a value the browser chose.
expect_forwarded_for() {
    local sent="$1" want="$2" got seen
    got=$(docker exec "lms-stub-$TAG" python /ask.py POST /muma/api/auth/login "$sent" 2>&1 || true)
    seen=$(printf '%s' "$got" | sed -n 's/.*"x_forwarded_for": "\([^"]*\)".*/\1/p')
    if [ "$seen" = "$want" ]; then
        echo "ok    X-Forwarded-For '$sent' -> MuMa sees '$seen'"
    else
        echo "FAIL  X-Forwarded-For '$sent' -> MuMa sees '$seen'; want '$want'"
        failures=$((failures + 1))
    fi
}

expect_forwarded_for "198.51.100.7"                          "198.51.100.7"
expect_forwarded_for "203.0.113.9, 198.51.100.7"             "198.51.100.7"
expect_forwarded_for "203.0.113.9, 198.51.100.7, 172.16.0.30"   "198.51.100.7"

if [ "$failures" -ne 0 ]; then
    echo "$failures routing case(s) failed"
    exit 1
fi
echo "--- reverse proxy routing OK ---"
