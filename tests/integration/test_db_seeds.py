"""services/common/db_seeds.seed() against a real MariaDB.

The unit test proves the splitter and the order; only MariaDB proves that the seed files run,
insert the rows a new database needs, and insert nothing on the next start.
"""

import pytest

from services.common.db_seeds import seed
from tests.integration.conftest import run_sql

pytestmark = pytest.mark.integration

#: Rows per table after one seed() on an empty database (measured 2026-10-29).
EXPECTED_COUNTS = {
    'rules_genres': 33,
    'rules_festivals': 92,
    'rules_festival_aliases': 118,
    'rules_label_name_choices': 104,
    'rules_artists': 11,
    'rules_ignored_artists': 11,
    'rules_scene_group_date_format': 5,
    'radio_stations': 67,
}


def _seed(connection):
    with connection.cursor() as cursor:
        seed(cursor)


def _counts(connection):
    return {table: run_sql(connection, f'SELECT COUNT(*) AS n FROM `{table}`')[0]['n'] for table in EXPECTED_COUNTS}


def _content(connection, table):
    """Every row of `table` without auto ids and timestamps, sorted, so two databases compare.

    An alias names its festival by name instead of by id, since ids depend on insert order.
    """
    columns = [
        row['Field']
        for row in run_sql(connection, f'SHOW COLUMNS FROM `{table}`')
        if 'auto_increment' not in row['Extra'].lower()
        and not row['Type'].lower().startswith(('timestamp', 'datetime'))
    ]
    if table == 'rules_festival_aliases':
        select = ', '.join('f.name AS festival' if c == 'festival_id' else f'a.`{c}`' for c in columns)
        rows = run_sql(
            connection, f'SELECT {select} FROM rules_festival_aliases a JOIN rules_festivals f ON f.id = a.festival_id'
        )
    else:
        rows = run_sql(connection, f'SELECT {", ".join(f"`{c}`" for c in columns)} FROM `{table}`')
    return sorted(tuple(sorted((key, str(value)) for key, value in row.items())) for row in rows)


def _all_content(connection):
    return {table: _content(connection, table) for table in EXPECTED_COUNTS}


def test_seed_inserts_the_reference_rows_of_a_new_database(db):
    _seed(db)

    assert _counts(db) == EXPECTED_COUNTS


def test_seed_twice_more_changes_nothing(db):
    _seed(db)
    before = _all_content(db)

    _seed(db)
    _seed(db)

    assert _counts(db) == EXPECTED_COUNTS
    assert _all_content(db) == before


def test_a_row_a_curator_edited_stays_edited_after_another_seed(db):
    _seed(db)
    run_sql(
        db,
        "UPDATE rules_genres SET name = 'YouTube Music', state = 'white', decided_by = 'curator' "
        "WHERE normalized_name = 'music'",
    )
    run_sql(db, "UPDATE rules_festivals SET name = 'Defqon.1' WHERE normalized_name = 'defqon'")
    run_sql(db, "UPDATE rules_label_name_choices SET chosen_folder = 'Cloud 9 Dance' WHERE nfo_label_key = 'cloud9'")
    run_sql(db, "UPDATE rules_ignored_artists SET corrected_name = 'Teasers' WHERE name = 'Teaser'")
    run_sql(db, "UPDATE rules_artists SET state = 'white', decided_by = 'curator' WHERE name = 'Video'")
    run_sql(db, "UPDATE rules_scene_group_date_format SET date_format = 'dm' WHERE scene_group = 'AOV'")

    _seed(db)

    assert _counts(db) == EXPECTED_COUNTS
    genre = run_sql(db, "SELECT name, state, decided_by FROM rules_genres WHERE normalized_name = 'music'")
    assert genre == [{'name': 'YouTube Music', 'state': 'white', 'decided_by': 'curator'}]
    assert run_sql(db, "SELECT name FROM rules_festivals WHERE normalized_name = 'defqon'") == [{'name': 'Defqon.1'}]
    assert run_sql(db, "SELECT chosen_folder FROM rules_label_name_choices WHERE nfo_label_key = 'cloud9'") == [
        {'chosen_folder': 'Cloud 9 Dance'}
    ]
    assert run_sql(db, "SELECT corrected_name FROM rules_ignored_artists WHERE name = 'Teaser'") == [
        {'corrected_name': 'Teasers'}
    ]
    assert run_sql(db, "SELECT state, decided_by FROM rules_artists WHERE name = 'Video'") == [
        {'state': 'white', 'decided_by': 'curator'}
    ]
    assert run_sql(db, "SELECT date_format FROM rules_scene_group_date_format WHERE scene_group = 'AOV'") == [
        {'date_format': 'dm'}
    ]


def test_seed_does_not_copy_later_ignored_artists_into_rules_artists(db):
    run_sql(db, "INSERT INTO rules_ignored_artists (name, corrected_name) VALUES ('Some Channel', NULL)")

    _seed(db)

    assert not run_sql(db, "SELECT name FROM rules_artists WHERE name = 'Some Channel'")


# --- Equivalence with the migrations -----------------------------------------------------------


def test_the_second_station_batch_keeps_the_first_three_at_the_top(db):
    """The batch starts its order after the first seed, and changes no row."""
    _seed(db)
    rows = run_sql(db, 'SELECT slug FROM radio_stations ORDER BY sort_order, slug')
    slugs = [row['slug'] for row in rows]
    assert slugs[:5] == ['slam', 'q-dance', '538', '100-nl', '100-nl-non-stop']


def test_a_removed_station_of_the_second_batch_does_not_come_back(db):
    """The batch adds its stations once, so a curator's removal stays."""
    _seed(db)
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM radio_stations WHERE slug = 'sky-radio'")
    _seed(db)
    slugs = {row['slug'] for row in run_sql(db, 'SELECT slug FROM radio_stations')}
    assert 'sky-radio' not in slugs
    assert 'qmusic' in slugs


def test_a_removed_radio_station_does_not_come_back(db):
    """The seed only fills an empty table, so a curator's choice survives the next start."""
    _seed(db)
    with db.cursor() as cursor:
        cursor.execute("DELETE FROM radio_stations WHERE slug = '538'")
    _seed(db)
    slugs = {row['slug'] for row in run_sql(db, 'SELECT slug FROM radio_stations')}
    assert '538' not in slugs
    assert {'slam', 'q-dance'} <= slugs
