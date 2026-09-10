"""A Room schema that changes shape has to change version with it.

6.32.0 added three columns to the track entity and left `version = 8` alone, so Room
regenerated `8.json` in place with a new identity hash. Every phone that had filled its
cache before that build then refused to open its own database -- "Room cannot verify the
data integrity" -- and the app reported it as a connection error on every screen that
touches the metadata cache. Nothing in the pipeline noticed: the schema export is just a
tracked file, and rewriting one is a clean diff.

`identity-hashes.json` is what makes that diff loud. An entry belongs to a version that
has shipped, so changing one means a database in the field no longer matches the code
that has to open it.
"""

import json
import re
from pathlib import Path

import pytest

SCHEMAS = Path(__file__).resolve().parents[2] / "services/muma-mobile/app/schemas"
LOCK = SCHEMAS / "identity-hashes.json"
SOURCE = Path(__file__).resolve().parents[2] / "services/muma-mobile/app/src/main/kotlin/nl/teunschriks/mumamobile/data"


def exported_schemas():
    for database in sorted(SCHEMAS.iterdir()):
        if not database.is_dir():
            continue
        for schema in sorted(database.glob("*.json"), key=lambda path: int(path.stem)):
            yield f"{database.name}/{schema.stem}", schema


def test_every_exported_schema_is_locked():
    locked = json.loads(LOCK.read_text())
    exported = {key: json.loads(path.read_text())["database"]["identityHash"] for key, path in exported_schemas()}

    assert exported == locked, (
        "An exported Room schema no longer matches identity-hashes.json.\n"
        "A new key is fine: add it. A changed hash is not -- it means the entities moved\n"
        "under a version number that is already installed on phones. Bump the database\n"
        "version instead, add the migration, and leave the old export alone."
    )


@pytest.mark.parametrize("database", ["AppDatabase", "MetaDatabase"])
def test_declared_version_has_an_export(database):
    source = (SOURCE / f"{database}.kt").read_text()
    version = int(re.search(r"version = (\d+)", source).group(1))
    exported = {int(path.stem) for path in (SCHEMAS / f"nl.teunschriks.mumamobile.data.{database}").glob("*.json")}

    assert version in exported, (
        f"{database} declares version {version} but exports {sorted(exported)}. "
        "Build the app so Room writes the schema, and commit it."
    )
    assert max(exported) == version, (
        f"{database} exports a schema for version {max(exported)} while declaring {version}."
    )
