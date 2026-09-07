#!/bin/bash
# scripts/lib/e2e-stack.sh
#
# Brings up docker/compose.test.yml with a fixture track in the music volume,
# and tears it down again.
#
# It was extracted when two suites ran against the same stack and had to start
# it identically; only scripts/test/core-e2e.sh is left. It stays a file of its
# own because bringing the stack up and deciding what to run against it are two
# jobs, and the first half is the larger one: an LMS user, a declared library
# and a completed scan all have to exist before the suite can ask LMS anything
# at all. See e2e_stack_scan_lms below.
#
# Usage:
#
#   source "$ROOT_DIR/scripts/lib/e2e-stack.sh"
#   e2e_stack_up muma-e2e      # project-name prefix, so two runs can coexist
#   ... run tests ...
#
# e2e_stack_up exports MUMA_TEST_PORT_MANAGER, MUMA_TEST_PORT_LMS and
# COMPOSE_PROJECT_NAME, which is what the suites read to find the stack, and
# registers the teardown on EXIT. The caller does not clean up.

E2E_STACK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
E2E_STACK_COMPOSE_FILE="$E2E_STACK_ROOT/docker/compose.test.yml"
E2E_STACK_FIXTURE="$E2E_STACK_ROOT/tests/fixtures/music/ci-test-track-001.mp3"
# Where the fixture sits inside the LMS container (/music) and, through the shared
# volume, under music-manager's /mnt/music. See the copy step below for why it is
# a subfolder. tests/bdd reads the same location as MUMA_TEST_FIXTURE_DIR.
E2E_STACK_FIXTURE_DIR="/music/Top 100"
MUMA_TEST_FIXTURE_DIR="/mnt/music/Top 100"
export MUMA_TEST_FIXTURE_DIR

# The second fixture: a label release, in the three-level shape the label chain reads
# its publisher and catalogue number out of -- <eps root>/<label>/<cat id - release>/.
# It carries no genre and no publisher of its own, so everything the library ends up
# knowing about it came from a rule rather than from a tag. See tests/fixtures/README.md
# and tests/bdd/features/label_import.feature.
E2E_STACK_EP_FIXTURE="$E2E_STACK_ROOT/tests/fixtures/music/ci-test-ep-001.mp3"
E2E_STACK_EP_RELEASE="TEX001 - Lil_Texas_and_Albino_-_Gabber_Cowboy-WEB-2026-SRG"
E2E_STACK_EP_DIR="/music/EPs/Texcore/$E2E_STACK_EP_RELEASE"
MUMA_TEST_EP_PATH="/mnt/music/EPs/Texcore/$E2E_STACK_EP_RELEASE/01-gabber_cowboy.mp3"
export MUMA_TEST_EP_PATH

# Picking a free port rather than a fixed one is what keeps two pipelines from
# killing each other's run; see docs/testing-inventory.md and the backend:integration
# collision it is modelled on.
e2e_stack_find_free_port() {
    python3 -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}

e2e_stack_down() {
    echo "--- Tearing down the e2e stack ---"
    # --rmi local for the same reason contracts.sh does it: without it every run
    # leaves a pair of images behind under its own project name and eventually
    # fills the runner's disk.
    $E2E_STACK_COMPOSE down -v --remove-orphans --rmi local
}

# e2e_stack_up <project-name-prefix>
e2e_stack_up() {
    local prefix="${1:?e2e_stack_up needs a compose project-name prefix}"

    # CI_JOB_ID keeps concurrent pipelines apart; the prefix keeps two suites on
    # one machine apart, which is what happens when both are run locally.
    COMPOSE_PROJECT_NAME="${prefix}${CI_JOB_ID:+-}${CI_JOB_ID:-}"
    export COMPOSE_PROJECT_NAME

    MUMA_TEST_PORT_MANAGER=$(e2e_stack_find_free_port)
    MUMA_TEST_PORT_LMS=$(e2e_stack_find_free_port)
    export MUMA_TEST_PORT_MANAGER
    export MUMA_TEST_PORT_LMS

    # The account e2e_stack_scan_lms creates and the suite authenticates as. It
    # exists only inside a stack that is destroyed at the end of the run, and
    # the credentials have to be readable by both halves, so they are plain
    # here rather than pretending to be a secret.
    MUMA_TEST_LMS_USER="${MUMA_TEST_LMS_USER:-e2e-admin}"
    MUMA_TEST_LMS_PASSWORD="${MUMA_TEST_LMS_PASSWORD:-e2e-password}"
    export MUMA_TEST_LMS_USER
    export MUMA_TEST_LMS_PASSWORD

    echo "--- Using dynamic ports: Manager=$MUMA_TEST_PORT_MANAGER, LMS=$MUMA_TEST_PORT_LMS ---"

    E2E_STACK_COMPOSE="docker compose -f $E2E_STACK_COMPOSE_FILE -p $COMPOSE_PROJECT_NAME"
    trap e2e_stack_down EXIT

    echo "--- Building and starting the stack from a clean state ---"
    $E2E_STACK_COMPOSE down -v --remove-orphans 2>/dev/null || true
    $E2E_STACK_COMPOSE up -d --build

    echo "--- Waiting for services to become healthy ---"
    local deadline=$((SECONDS + 300))
    local service cid status
    for service in $($E2E_STACK_COMPOSE config --services); do
        while true; do
            cid=$($E2E_STACK_COMPOSE ps -q "$service")
            status=$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "none")
            [ "$status" = "healthy" ] && { echo "OK: $service is healthy"; break; }
            if [ "$status" = "unhealthy" ] || [ $SECONDS -ge $deadline ]; then
                echo "ERROR: $service did not become healthy in time (status: $status)"
                $E2E_STACK_COMPOSE logs "$service"
                exit 1
            fi
            sleep 2
        done
    done

    e2e_stack_apply_migrations

    # The fixture lands on the shared volume, which music-manager's scanner walks
    # on demand (/api/scanner/scan/all, which the suite calls).
    #
    # Under "Top 100" rather than loose in the root. The scanner walks the whole
    # volume, but the tagger's full run does not: it visits the label folders,
    # the download channels and a fixed list of generic folders (Livesets,
    # Podcasts, Top 100, Warm Up Mixes), which is what the library actually
    # looks like. A file in the root is therefore scanned but never retagged,
    # and the retag feature waited on a queue that could not drain. Top 100 is
    # the generic folder whose name implies the least about the file.
    echo "--- Copying the fixture track into the LMS music volume ---"
    local lms_cid
    lms_cid=$($E2E_STACK_COMPOSE ps -q music-management-server)
    docker exec -u 0 "$lms_cid" mkdir -p "$E2E_STACK_FIXTURE_DIR"
    docker cp "$E2E_STACK_FIXTURE" "$lms_cid":"$E2E_STACK_FIXTURE_DIR/ci-test-track-001.mp3"

    e2e_stack_place_release "$lms_cid"
    e2e_stack_seed_curation
    e2e_stack_tag_fixture
    e2e_stack_scan_lms
}

# The label release, and the import queue folder beside it.
#
# `__TODO` is created empty on purpose: it is `import_folder_path`, it sits inside the
# EPs tree, and the tagger's underscore guard is what keeps a release still waiting
# there from having `__TODO` written into it as its publisher. An empty folder is
# enough for that guard to be exercised rather than skipped.
#
# The NFO is what carries the exact release date. The file has a bare year in its tag,
# which is all a scene rip ever states, and `Street Date` in the NFO next to it is the
# only place the day is written down.
e2e_stack_place_release() {
    local lms_cid="$1"
    echo "--- Placing the label release fixture under the EPs tree ---"
    docker exec -u 0 "$lms_cid" mkdir -p "$E2E_STACK_EP_DIR" /music/EPs/__TODO
    docker cp "$E2E_STACK_EP_FIXTURE" "$lms_cid":"$E2E_STACK_EP_DIR/01-gabber_cowboy.mp3"
    docker exec -u 0 "$lms_cid" sh -c \
        "printf '%s\n' '  Street Date ......: 10-09-2026' '  Rip Date .........: 08-09-2026' > '$E2E_STACK_EP_DIR/00-release.nfo'"
}

# Two decided genres, so the scenario has something to point its rules at.
#
# Written in SQL rather than over the API because there is no way to create a genre
# over the API at all: a row only enters `rules_genres` when the tagger meets the name
# in a file and files it as unknown (ResolveGenreRule.record_unknown), and the release
# fixture deliberately carries no genre tag -- that is the whole point of it. The
# decision itself is what the scenario would otherwise have to fake; everything the
# feature actually asserts is written and read over HTTP.
e2e_stack_seed_curation() {
    echo "--- Seeding two decided genres for the label-import feature ---"
    local db_cid
    db_cid=$($E2E_STACK_COMPOSE ps -q test-db)
    docker exec -i "$db_cid" mariadb -uroot -ptest-root-password muma_test <<'SQL'
INSERT IGNORE INTO rules_genres (name, normalized_name, state, decided_by, decided_at)
VALUES ('Uptempo Hardcore', 'uptempo hardcore', 'white', 'e2e-seed', NOW()),
       ('Hardcore', 'hardcore', 'white', 'e2e-seed', NOW());
SQL
}

# The tagger, before anything indexes the file, because it rewrites it.
#
# Two reasons it has to happen here rather than inside a scenario. It is the only
# thing that ever registers a genre for curation -- record_unknown() is called
# from services/tagger/Song/rules/ResolveGenreRule.py and nowhere else -- so
# without it the fixture's Electronic tag resolves to nothing and every track in
# the library comes back genre-less. And it changes the file's bytes: run it
# after LMS has scanned and LMS keeps serving the new file while reporting the
# old size, which is exactly the disagreement the streaming scenario asserts
# against.
e2e_stack_tag_fixture() {
    echo "--- Tagging the fixture, before either index is built ---"
    local key="${API_KEY:-test-api-key}"
    # The folder name carries a space; the only character in the path that needs
    # encoding, so it is done by hand rather than pulling in a URL library.
    local fixture_path="$MUMA_TEST_FIXTURE_DIR/ci-test-track-001.mp3"
    curl -sf -X POST -H "x-api-key: $key" \
        "http://127.0.0.1:$MUMA_TEST_PORT_MANAGER/api/tagger/tag/file?path=${fixture_path// /%20}" \
        >/dev/null
}

# scripts/deploy.sh applies every migrate_*.sql on each deploy, so production's
# schema is db_init plus all of them. This stack was running db_init alone, and
# the difference is not cosmetic: the migrations are what seed `rules_genres`,
# and nothing in services/ ever inserts into it. Without them that table stays
# empty, the scanner can map no tag onto a genre id, `library_track_genres` stays
# empty too, and every track comes back genre-less -- so a whole feature area was
# switched off in the only test that walks the real stack, in a way that looked
# like the fixture simply having no tags.
#
# Applied here rather than in compose so the order is the same as the deploy's:
# the services have already created their tables by the time this runs.
e2e_stack_apply_migrations() {
    echo "--- Applying migrate_*.sql, the way a deploy does ---"
    local db_cid
    db_cid=$($E2E_STACK_COMPOSE ps -q test-db)
    local migration
    for migration in "$E2E_STACK_ROOT"/migrate_*.sql; do
        [ -e "$migration" ] || continue
        # Credentials are docker/compose.test.yml's, for a database that exists
        # for the length of one job and holds nothing but the fixture.
        if ! docker exec -i "$db_cid" \
            mariadb -uroot -ptest-root-password muma_test < "$migration"; then
            echo "ERROR: $(basename "$migration") failed to apply"
            exit 1
        fi
    done
}

# LMS keeps its own index, entirely separate from music-manager's. Until this
# ran, the file was on LMS's disk without being in its library, and the suite's
# Subsonic step could only assert that the request was answered.
#
# "Answered" turned out to mean less than it sounds: Subsonic reports failures
# inside a 200, so searching as a user that was never created returned
#
#   {"status":"failed","error":{"code":40,"message":"Wrong username or password."}}
#
# and the assertion passed on it. The four steps below are what it takes to make
# that step mean something: LMS has no users of its own -- music-manager owns
# them and pushes them across -- so an account has to exist before anything can
# be asked of the Subsonic API at all, and a library has to be declared before a
# scan has anywhere to look. Same sequence as scripts/test/frontend-browser.sh,
# which needed it first.
e2e_stack_scan_lms() {
    local manager="http://127.0.0.1:$MUMA_TEST_PORT_MANAGER"
    local lms="http://127.0.0.1:$MUMA_TEST_PORT_LMS"
    local subsonic="u=$MUMA_TEST_LMS_USER&p=$MUMA_TEST_LMS_PASSWORD&v=1.16.1&c=e2e-test&f=json"

    echo "--- Creating the LMS user ---"
    curl -sf -X POST "$manager/api/auth/setup" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$MUMA_TEST_LMS_USER\",\"password\":\"$MUMA_TEST_LMS_PASSWORD\"}" >/dev/null

    echo "--- Waiting for the user to sync into LMS ---"
    local deadline=$((SECONDS + 60))
    local status
    while true; do
        status=$(curl -s "$lms/rest/ping.view?$subsonic" \
            | python3 -c "import json,sys; print(json.load(sys.stdin)['subsonic-response']['status'])" 2>/dev/null || echo "")
        [ "$status" = "ok" ] && break
        if [ $SECONDS -ge $deadline ]; then
            echo "ERROR: the user never reached LMS, so nothing can authenticate against it"
            $E2E_STACK_COMPOSE logs music-management-server
            exit 1
        fi
        sleep 1
    done

    echo "--- Declaring the music library and scanning it ---"
    curl -sf -X POST "$lms/muma/api/admin/libraries?u=$MUMA_TEST_LMS_USER&p=$MUMA_TEST_LMS_PASSWORD" \
        -H "Content-Type: application/json" \
        -d '{"name":"e2e-library","path":"/music"}' >/dev/null
    curl -sf "$lms/rest/startScan.view?$subsonic" >/dev/null

    # The scan is asynchronous and takes well under a second for one file, but
    # polling for the track rather than for "not scanning" is what actually
    # answers the question: an empty library also reports that it is not
    # scanning.
    echo "--- Waiting for LMS to index the fixture track ---"
    deadline=$((SECONDS + 60))
    local found
    while true; do
        found=$(curl -s "$lms/rest/search3.view?query=CI%20Test%20Track&$subsonic" \
            | python3 -c "import json,sys; d=json.load(sys.stdin); print(bool(d['subsonic-response'].get('searchResult3',{}).get('song')))" 2>/dev/null || echo "False")
        [ "$found" = "True" ] && { echo "OK: LMS has the fixture track"; break; }
        if [ $SECONDS -ge $deadline ]; then
            echo "ERROR: LMS never indexed the fixture track"
            $E2E_STACK_COMPOSE logs music-management-server
            exit 1
        fi
        sleep 2
    done
}
