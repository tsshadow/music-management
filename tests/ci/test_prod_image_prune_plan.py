"""What the production image prune is allowed to delete (bug report 094).

The planner is a pure function over a listing, so each rule that protects
production -- a used image, the rollback window, the nightly backup's image --
is checked here without a Docker daemon. The shell around it is exercised in
test_deploy_disk_and_db_safety.py.
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "prod_image_prune_plan.py"

_spec = importlib.util.spec_from_file_location("prod_image_prune_plan", MODULE_PATH)
assert _spec and _spec.loader
planner = importlib.util.module_from_spec(_spec)
# Registered before exec: @dataclass resolves annotations through sys.modules.
sys.modules["prod_image_prune_plan"] = planner
_spec.loader.exec_module(planner)


def image(image_id: str, created: str, *refs: str) -> list[str]:
    """Listing lines for one image: its build time, then tags (`r:t`) and digests (`r@...`)."""
    lines = [f"image\t{image_id}\t{created}"]
    for ref in refs:
        lines.append(f"{'digest' if '@' in ref else 'tag'}\t{image_id}\t{ref}")
    return lines


def test_a_used_image_is_never_removed_even_when_old_and_untagged() -> None:
    lines = ["container\tsha256:old", *image("sha256:old", "2020-01-01T00:00:00Z")]
    removals, kept = planner.plan(lines, keep=1)
    assert removals == []
    assert "used by a container" in kept[0]


def test_previous_releases_are_ranked_by_build_time_per_repository() -> None:
    lines = [
        "container\tsha256:run",
        *image("sha256:run", "2026-09-25T10:00:00Z", "u/app:latest"),
        *image("sha256:p1", "2026-09-24T10:00:00+02:00", "u/app@sha256:1"),
        *image("sha256:p2", "2026-09-23T10:00:00.123456789Z", "u/app@sha256:2"),
        *image("sha256:p3", "2026-09-22T10:00:00Z", "u/app@sha256:3"),
        *image("sha256:other", "2026-01-01T00:00:00Z", "u/other@sha256:9"),
    ]
    removals, _ = planner.plan(lines, keep=2)
    assert removals == ["sha256:p3"], "p1, p2 are the rollback window; u/other has its own window"


def test_an_image_without_a_build_time_is_given_up_first() -> None:
    lines = [
        *image("sha256:new", "2026-09-24T10:00:00Z", "u/app@sha256:1"),
        *image("sha256:unknown", "garbage", "u/app@sha256:2"),
    ]
    assert planner.plan(lines, keep=1)[0] == ["sha256:unknown"]


def test_moving_tags_are_kept_and_version_tags_removed_by_reference() -> None:
    lines = [
        *image("sha256:t", "2026-09-01T00:00:00Z", "u/tools:latest"),
        *image("sha256:n", "2026-09-25T00:00:00Z", "u/tools:0.72.2"),
        *image("sha256:v", "2026-08-01T00:00:00Z", "u/tools:0.50.0", "u/tools:0.50", "u/tools@sha256:5"),
    ]
    removals, kept = planner.plan(lines, keep=1)
    assert removals == ["u/tools:0.50.0", "u/tools:0.50"]
    assert any("moving tag" in line for line in kept)


def test_dangling_images_without_a_repository_go() -> None:
    assert planner.plan(image("sha256:d", "2026-09-25T00:00:00Z"), keep=3)[0] == ["sha256:d"]


def test_a_registry_port_is_not_mistaken_for_a_tag() -> None:
    assert planner.split_tag("registry:5000/u/app:1.2") == ("registry:5000/u/app", "1.2")
    assert planner.split_tag("registry:5000/u/app") is None


def test_main_refuses_keep_zero(capsys) -> None:
    try:
        planner.main(["--keep", "0"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("--keep 0 must be refused")
    assert "at least 1" in capsys.readouterr().err
