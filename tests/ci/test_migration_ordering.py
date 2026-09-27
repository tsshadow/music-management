"""Migrations must be expand-only, because they now run before the new code.

scripts/deploy.sh applies every migrate_*.sql while the *previous* release's
containers are still running, and only then recreates them (bug report 050).
That order is only safe when a migration leaves the schema usable by the code
that is already running: adding tables, columns and indexes is fine; dropping,
renaming or narrowing something the old code still reads is not. Such a
"contract" step belongs in a later release, once no running code uses the old
shape -- see docs/deployment.md#deploy-order-and-migrations.

The files listed in ALREADY_APPLIED predate that order. Each contains a
statement matched below, and each has long since been applied to production;
their guards (IF EXISTS, information_schema checks, keys on legacy values)
make every re-run a no-op, so running them before `up` changes nothing. A new
file does not get onto this list by default: a contract step needs its own
release, and a reviewer should see that decision in the diff.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools import apply_migrations

REPO_ROOT = Path(__file__).resolve().parents[2]

# Statements that remove, rename or narrow schema or data the running release
# may still use. DROP TEMPORARY TABLE and the underscore-prefixed scratch seed
# tables (_festival_seed...) are the migration's own scaffolding, not schema.
CONTRACT_PATTERNS = [
    re.compile(
        r"\bDROP\s+(?!TEMPORARY\b)(?:TABLE|COLUMN|INDEX|KEY|PRIMARY\s+KEY|VIEW)\b(?!\s+(?:IF\s+EXISTS\s+)?_)", re.I
    ),
    re.compile(r"\bRENAME\s+(?:TABLE|COLUMN|INDEX|KEY|TO)\b", re.I),
    re.compile(r"\bCHANGE\s+(?:COLUMN\s+)?`?\w+`?\s+`?\w+`?\s+\w", re.I),
    re.compile(r"\bMODIFY\b", re.I),
    re.compile(r"\bTRUNCATE\b", re.I),
    re.compile(r"\bDELETE\s+(?:\w+\s+)?FROM\b", re.I),
]

ALREADY_APPLIED = {
    "migrate_v2.sql",
    "migrate_v3_genre_states.sql",
    "migrate_v5_events.sql",
    "migrate_v6_youtube_video.sql",
    "migrate_v13_channels_binary_collation.sql",
    "migrate_v13_curation_edits.sql",
    "migrate_v19_work_key_binary.sql",
    "migrate_v29_processed_mtime_double.sql",
}

# Newer files whose matched statement was reviewed and is safe to run while the
# previous release is up, each with the reason a reviewer accepted. Unlike
# ALREADY_APPLIED these need not have reached production yet; the reason is what
# gets them here, and it has to hold for the release that is still running.
REVIEWED_SAFE = {
    "migrate_v33_listened_at_no_on_update.sql": (
        "MODIFY keeps listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP and only drops the "
        "implicit ON UPDATE, which no code relies on (it is bug 039); conditional on "
        "information_schema, so it is a no-op once applied, and scrobbler.init_db does the same "
        "on start-up of the previous release anyway"
    ),
    "migrate_v36_schema_drift.sql": (
        "conditional repairs of drift between db_init.py and production (bug 047): the DELETE "
        "removes duplicate rules_ignored_artists names before the plain index becomes the UNIQUE "
        "key production already has, and the previous release only reads that table by name; the "
        "DROP COLUMN removes five library_track_audio_features columns only fresh stacks ever had "
        "and nothing reads or writes, guarded on information_schema so production's table is "
        "never rebuilt"
    ),
    "migrate_v37_processed_files_binary_path.sql": (
        "the MODIFY only changes the collation of tagger_processed_files.filepath from "
        "utf8mb4_general_ci to utf8mb4_bin, same type and length; the previous release reads that "
        "table by exact path (needs_processing, mark_processed, the snapshot) and pages it in key "
        "order, all of which keep working, and a binary key is strictly finer so no existing row "
        "can collide; conditional on information_schema, so it is a no-op once applied (bug 051)"
    ),
    "migrate_v46_importer_file_problems.sql": (
        "the MODIFY only appends 'extractor' to the end of importer_conflicts.step's ENUM, keeping "
        "'renamer' and 'mover' and NOT NULL; the previous release only ever writes those two and "
        "reads rows by step, so nothing it does changes, and appending an ENUM value is a "
        "metadata-only ALTER that is a no-op when re-run (bug 119)"
    ),
    "migrate_v48_channel_link_manual_source.sql": (
        "the MODIFY only appends 'manual' to the end of channel_link_proposals.source's ENUM, "
        "keeping 'name', 'alias', 'redirect' and NOT NULL; the previous release only ever writes "
        "those three and lists rows without filtering on source, so nothing it does changes, and "
        "appending an ENUM value is a metadata-only ALTER that is a no-op when re-run (issue #58)"
    ),
}


def _statements(path: Path) -> str:
    """The file's SQL with `--` comments removed, so prose cannot match."""
    return "\n".join(line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())


def _contract_steps(path: Path) -> list[str]:
    """Every contract statement in PATH, as the text that matched."""
    sql = _statements(path)
    return [match.group(0) for pattern in CONTRACT_PATTERNS for match in pattern.finditer(sql)]


def test_new_migrations_are_expand_only() -> None:
    offenders = {
        path.name: _contract_steps(path)
        for path in sorted(REPO_ROOT.glob("migrate_*.sql"))
        if path.name not in ALREADY_APPLIED and path.name not in REVIEWED_SAFE and _contract_steps(path)
    }
    assert offenders == {}, (
        "these migrations drop, rename or narrow something while the previous release is still "
        f"running (scripts/deploy.sh migrates before `up`): {offenders}. "
        "Ship the contract step in a later release; see docs/deployment.md."
    )


def test_the_allowlist_only_names_files_that_need_it() -> None:
    """A stale entry would let a future edit of that file through unreviewed."""
    stale = [
        name
        for name in sorted(ALREADY_APPLIED | set(REVIEWED_SAFE))
        if not (REPO_ROOT / name).exists() or not _contract_steps(REPO_ROOT / name)
    ]
    assert stale == [], f"remove these from ALREADY_APPLIED / REVIEWED_SAFE: {stale}"
    assert not ALREADY_APPLIED & set(REVIEWED_SAFE), "a file belongs on one list, not both"


def test_the_patterns_catch_what_they_are_for(tmp_path: Path) -> None:
    samples = {
        "ALTER TABLE t DROP COLUMN c;": True,
        "DROP TABLE notifications;": True,
        "DROP TABLE IF EXISTS notifications;": True,
        "ALTER TABLE t MODIFY COLUMN c INT;": True,
        "ALTER TABLE t CHANGE genre name VARCHAR(100);": True,
        "RENAME TABLE a TO b;": True,
        "DELETE r FROM rules r JOIN d ON r.id = d.id;": True,
        "DROP TEMPORARY TABLE IF EXISTS scratch;": False,
        "DROP TABLE IF EXISTS _festival_seed;": False,
        "ALTER TABLE t ADD COLUMN IF NOT EXISTS c INT;": False,
        "CREATE TABLE IF NOT EXISTS t (id INT, FOREIGN KEY (x) REFERENCES y(id) ON DELETE CASCADE);": False,
        "-- we used to DROP TABLE here": False,
    }
    for sql, expected in samples.items():
        path = tmp_path / "migrate_sample.sql"
        path.write_text(sql + "\n", encoding="utf-8")
        assert bool(_contract_steps(path)) is expected, sql


# --- the ledger (bug report 068) ------------------------------------------------
#
# scripts/deploy.sh no longer runs every file on every deploy: tools/apply_migrations.py
# skips a file whose name and sha256 are in schema_migrations. Editing an applied file
# therefore re-runs it on the next deploy (new hash), which is why every file must stay
# re-runnable even though most deploys no longer run it.


def test_the_deploy_applies_migrations_through_the_ledger() -> None:
    deploy = (REPO_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert 'tools/apply_migrations.py" --password-stdin --exec run_remote_sql' in deploy
    assert '"$PROJECT_ROOT"/migrate_*.sql' in deploy
    assert "--lock-wait-timeout" in deploy


def test_every_migration_name_can_be_recorded() -> None:
    """record_sql() refuses a name it would have to quote; that would fail the deploy after the file ran."""
    for path in sorted(REPO_ROOT.glob("migrate_*.sql")):
        migration = apply_migrations.Migration(path, apply_migrations.file_sha256(path), "new")
        assert path.name in apply_migrations.record_sql(migration)


def test_the_order_is_byte_wise_lexical_not_by_version_number() -> None:
    """migrate_v10_* runs before migrate_v2.sql, which runs before migrate_v29_*. Documented in
    docs/deployment.md; a migration must not depend on a higher-numbered one."""
    names = [p.name for p in sorted(REPO_ROOT.glob("migrate_*.sql"), key=lambda p: p.name.encode())]
    assert names.index("migrate_v10_audio_features_relink.sql") < names.index("migrate_v2.sql")
    assert names.index("migrate_v2.sql") < names.index("migrate_v29_processed_mtime_double.sql")
    deployment = (REPO_ROOT / "docs" / "deployment.md").read_text(encoding="utf-8")
    assert "`migrate_v10_audio_features_relink.sql` before `migrate_v2.sql`" in deployment
