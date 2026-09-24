#!/bin/bash
# scripts/typecheck.sh
# Runs mypy over the Python services.
#
# Rolled out per module rather than all at once. pyproject.toml sets a loose
# floor for the whole tree and a [[tool.mypy.overrides]] block lists the modules
# that are checked strictly; that list only ever grows. Cleaning a module up
# means fixing its findings and adding it there in the same merge request.
#
# Usage: ./scripts/typecheck.sh [path ...]     (default: the strict module list)
#        ./scripts/typecheck.sh --all          (whole tree, at the loose floor)

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# shellcheck source=scripts/lib/python-tooling.sh
source "$ROOT_DIR/scripts/lib/python-tooling.sh"

# In CI always inside the tooling container (tooling_container_required),
# elsewhere only when mypy is missing from this host.
if tooling_container_required \
   || { [ "${PYTHON_TOOLING_CONTAINER:-0}" != "1" ] && ! have_tool mypy; }; then
    rerun_in_container ./scripts/typecheck.sh "$@"
fi

export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services:${PYTHONPATH:-}"

# The strict list, kept in step with [[tool.mypy.overrides]] in pyproject.toml.
STRICT_MODULES=(
    services/common/config_store.py
    services/common/step.py
    services/common/version_helper.py
    services/common/Helpers/ArtistNameAnalyzer.py
    services/common/Helpers/FestivalHelper.py
    services/common/Helpers/FilterTableHelper.py
    services/common/Helpers/GenreRulesHelper.py
    services/common/Helpers/LookupTableHelper.py
    services/common/Helpers/PodcastHelper.py
    services/common/Helpers/TableHelper.py
    services/downloader/account_schedule.py
    services/downloader/rate_state.py
    services/importer/extractor.py
    services/importer/renamer.py
    services/music_manager/rbac.py
    services/music_manager/feeds/
    services/music_manager/artist_image_fetcher/matcher.py
    services/music_manager/artist_image_fetcher/normalizer.py
    services/music_manager/artist_image_fetcher/storage.py
    services/music_manager/artist_image_fetcher/providers/base.py
    services/music_manager/catalog_series.py
    services/tagger/constants.py
    services/tagger/Song/rules/TagResult.py
    services/tagger/Song/rules/TagRule.py
)

if [ "${1:-}" = "--all" ]; then
    echo "--- mypy over the whole tree (loose floor) ---"
    # --explicit-package-bases: tools/ has no __init__.py, so without it mypy derived
    # "muma_mcp.api" from the path and "tools.muma_mcp.api" from the imports, called
    # the file "found twice under different module names" and checked nothing at all.
    # Nothing ran this in CI, so that went unnoticed; backend:typecheck-all runs it now.
    python3 -m mypy --explicit-package-bases services/ tools/
elif [ $# -gt 0 ]; then
    echo "--- mypy on: $* ---"
    python3 -m mypy "$@"
else
    echo "--- mypy on ${#STRICT_MODULES[@]} strictly-checked modules ---"
    python3 -m mypy "${STRICT_MODULES[@]}"
fi

echo "--- Type check passed ---"
