"""A fresh stack and a deployed one must end up with the same schema.

Two code paths build this database and nothing used to compare them. A fresh stack
(the test stack, a new install, every test in this directory) gets its tables from
the CREATE TABLE statements in services/common/db_init.py and the routers' init_db;
production got its tables years ago and has been moved forward since by the
migrate_*.sql files scripts/deploy.sh applies. A change made on one path only --
an index added to a CREATE but never migrated, a column a migration widens that the
CREATE still declares narrow -- was invisible: every test here ran against the
fresh-stack schema and passed, and production differed. See
docs/bug-reports/047-schema-drift-invisible-to-the-integration-suite.md.

This builds both from an empty database and compares them column by column and
index by index. What it cannot see is drift already baked into production's older
tables that neither path reproduces; that is what the known cases in the bug report
were, and why each of them now has a migration.
"""

import pytest

from tests.integration import schema_sources
from tests.integration.conftest import _apply_migrations

pytestmark = pytest.mark.integration


def test_a_fresh_stack_and_a_migrated_one_have_the_same_columns_and_indexes(built_schemas):
    problems = schema_sources.diff(built_schemas['code'], built_schemas['migrated'])
    assert not problems, 'schema drift between db_init/init_db and the migrations:\n  ' + '\n  '.join(problems)


def test_a_fresh_stack_creates_every_table_a_migration_creates(built_schemas):
    """A table only a migration declares exists in production and nowhere else, so
    every endpoint that reads it 500s on a fresh stack and in this suite."""
    missing = set(schema_sources.migration_declared_tables()) - set(built_schemas['code'])
    assert not missing, f'declared by a migration but not created by db_init/init_db: {sorted(missing)}'


def test_every_init_db_is_run_at_startup():
    """build_from_code follows main.py's startup; an init_db that is not called from there
    creates its tables in no fresh stack, only wherever somebody happened to call it."""
    # Not called from main.py directly, each with the reason that is fine.
    called_indirectly = {
        'services.music_manager.rbac': 'users.init_db calls rbac.init_db first',
        # Not called at all, and it does not need to be: its body is `pass`.
        'services.music_manager.routers.stats': 'a no-op kept for the router convention',
    }
    orphaned = schema_sources.modules_defining_init_db() - schema_sources.startup_init_db_modules()
    assert orphaned <= set(called_indirectly), f'init_db never called at startup: {sorted(orphaned)}'


def test_every_templated_table_name_is_resolved():
    assert schema_sources.unresolved_templates() == []


def _indexes_on(connection, table, column):
    """{index name: unique?} for the single-column indexes on `table`.`column`."""
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT index_name AS i, MAX(non_unique) AS nu FROM information_schema.statistics '
            'WHERE table_schema = DATABASE() AND table_name = %s GROUP BY index_name '
            'HAVING COUNT(*) = 1 AND MAX(column_name) = %s',
            (table, column),
        )
        return {row['i']: not row['nu'] for row in cursor.fetchall()}


def test_migrate_v36_makes_an_old_ignore_list_unique_and_keeps_the_newest_row(db):
    """A database built from the old CREATE has a plain INDEX(name) and may hold the same
    name twice. The migration removes the older copy and only then adds the unique key."""
    with db.cursor() as cursor:
        cursor.execute('ALTER TABLE rules_ignored_artists DROP INDEX name, ADD INDEX name (name)')
        cursor.execute("INSERT INTO rules_ignored_artists (name, corrected_name) VALUES ('Dj Promo', NULL)")
        cursor.execute("INSERT INTO rules_ignored_artists (name, corrected_name) VALUES ('DJ PROMO', 'DJ Promo')")
    assert _indexes_on(db, 'rules_ignored_artists', 'name') == {'name': False}

    _apply_migrations(db)
    _apply_migrations(db)

    assert _indexes_on(db, 'rules_ignored_artists', 'name') == {'name': True}
    with db.cursor() as cursor:
        cursor.execute("SELECT name, corrected_name FROM rules_ignored_artists WHERE name = 'dj promo'")
        assert cursor.fetchall() == [{'name': 'DJ PROMO', 'corrected_name': 'DJ Promo'}]


def test_migrate_v36_drops_the_audio_columns_nothing_fills(db):
    """Only fresh stacks ever had them; production never did, and nothing reads or writes them."""
    with db.cursor() as cursor:
        cursor.execute(
            'ALTER TABLE library_track_audio_features ADD COLUMN musical_key VARCHAR(20), ADD COLUMN energy FLOAT'
        )

    _apply_migrations(db)

    with db.cursor() as cursor:
        cursor.execute('SHOW COLUMNS FROM library_track_audio_features')
        columns = {row['Field'] for row in cursor.fetchall()}
    assert not {'musical_key', 'energy', 'danceability', 'valence', 'popularity'} & columns
