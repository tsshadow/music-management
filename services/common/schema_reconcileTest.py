"""Tests for services/common/schema_reconcile.py: what plan() adds and what it only reports."""

import unittest
from unittest import mock

from services.common import schema_reconcile
from services.common.schema_reconcile import Column, ForeignKey, Index, Schema, Table, plan, snapshot_lines

ID = Column('int(11)', 'NO', '<none>', 'auto_increment', '<none>')
NAME = Column('varchar(255)', 'NO', '<none>', '', 'utf8mb4_general_ci')
NOTE = Column('text', 'YES', 'NULL', '', 'utf8mb4_general_ci')
PRIMARY = Index(True, ('id',), 'BTREE')
BY_NAME = Index(False, ('name',), 'BTREE')

CREATE = (
    'CREATE TABLE `things` (\n'
    '  `id` int(11) NOT NULL AUTO_INCREMENT,\n'
    '  `name` varchar(255) NOT NULL,\n'
    '  `note` text DEFAULT NULL,\n'
    '  PRIMARY KEY (`id`),\n'
    '  KEY `idx_name` (`name`)\n'
    ') ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci'
)
VIEW = 'CREATE VIEW IF NOT EXISTS thing_names AS SELECT name FROM things'


def _table(columns=None, indexes=None, foreign_keys=None, collation='utf8mb4_general_ci') -> Table:
    """A table shaped like `things`, with any part replaced."""
    return Table(
        engine='InnoDB',
        collation=collation,
        columns=dict(columns if columns is not None else {'id': ID, 'name': NAME, 'note': NOTE}),
        indexes=dict(indexes if indexes is not None else {'PRIMARY': PRIMARY, 'idx_name': BY_NAME}),
        foreign_keys=set(foreign_keys or ()),
    )


def _declared() -> Schema:
    return Schema(tables={'things': _table()}, views={'thing_names'})


class PlanTest(unittest.TestCase):
    """plan() against a one-table declaration."""

    def setUp(self):
        patcher = mock.patch.multiple(
            schema_reconcile.schema_tables, TABLES=(('things', 'unused'),), VIEWS=(('thing_names', VIEW),)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _plan(self, live: Schema):
        return plan(_declared(), live, {'things': CREATE})

    def test_an_equal_database_needs_nothing(self):
        result = self._plan(_declared())
        self.assertEqual((result.statements, result.reports), ([], []))

    def test_a_missing_table_is_created_without_its_auto_increment(self):
        result = self._plan(Schema(views={'thing_names'}))
        self.assertEqual(len(result.statements), 1)
        self.assertTrue(result.statements[0].startswith('CREATE TABLE `things`'))
        self.assertNotIn('AUTO_INCREMENT=7', result.statements[0])

    def test_a_missing_column_is_added_after_the_column_before_it(self):
        live = Schema(tables={'things': _table(columns={'id': ID, 'note': NOTE})}, views={'thing_names'})
        self.assertEqual(
            self._plan(live).statements, ['ALTER TABLE `things` ADD COLUMN `name` varchar(255) NOT NULL AFTER `id`']
        )

    def test_a_missing_first_column_goes_first(self):
        live = Schema(tables={'things': _table(columns={'name': NAME, 'note': NOTE})}, views={'thing_names'})
        self.assertEqual(
            self._plan(live).statements, ['ALTER TABLE `things` ADD COLUMN `id` int(11) NOT NULL AUTO_INCREMENT FIRST']
        )

    def test_a_missing_index_is_added(self):
        live = Schema(tables={'things': _table(indexes={'PRIMARY': PRIMARY})}, views={'thing_names'})
        self.assertEqual(self._plan(live).statements, ['ALTER TABLE `things` ADD KEY `idx_name` (`name`)'])

    def test_an_index_under_another_name_counts_as_present(self):
        live = Schema(tables={'things': _table(indexes={'PRIMARY': PRIMARY, 'name': BY_NAME})}, views={'thing_names'})
        self.assertEqual(self._plan(live).statements, [])

    def test_a_missing_view_is_created(self):
        self.assertEqual(self._plan(Schema(tables={'things': _table()})).statements, [VIEW])

    def test_extra_objects_are_reported_never_dropped(self):
        live = Schema(
            tables={
                'things': _table(
                    columns={'id': ID, 'name': NAME, 'note': NOTE, 'legacy': NOTE},
                    indexes={'PRIMARY': PRIMARY, 'idx_name': BY_NAME, 'idx_note': Index(False, ('note(10)',), 'BTREE')},
                ),
                'old_things': _table(),
            },
            views={'thing_names', 'old_view'},
        )
        result = self._plan(live)
        self.assertEqual(result.statements, [])
        self.assertEqual(
            sorted(report.split(':')[0] for report in result.reports),
            ['extra column', 'extra index', 'extra table', 'extra view'],
        )

    def test_a_changed_column_primary_key_or_collation_is_reported_only(self):
        live = Schema(
            tables={
                'things': _table(
                    columns={'id': ID, 'name': NOTE, 'note': NOTE},
                    indexes={'PRIMARY': Index(True, ('id', 'name'), 'BTREE'), 'idx_name': BY_NAME},
                    collation='utf8mb4_unicode_ci',
                )
            },
            views={'thing_names'},
        )
        result = self._plan(live)
        self.assertEqual(result.statements, [])
        self.assertEqual(
            sorted(report.split(':')[0] for report in result.reports),
            ['changed column', 'changed primary key', 'changed table'],
        )

    def test_a_foreign_key_difference_is_reported_only(self):
        cascade = ForeignKey(('id',), 'others', ('id',), 'CASCADE', 'RESTRICT')
        set_null = ForeignKey(('id',), 'others', ('id',), 'SET NULL', 'RESTRICT')
        declared = Schema(tables={'things': _table(foreign_keys={set_null})}, views={'thing_names'})
        live = Schema(tables={'things': _table(foreign_keys={cascade})}, views={'thing_names'})
        result = plan(declared, live, {'things': CREATE})
        self.assertEqual(result.statements, [])
        self.assertEqual(
            sorted(report.split(':')[0] for report in result.reports), ['extra foreign key', 'missing foreign key']
        )


class SnapshotLinesTest(unittest.TestCase):
    """The snapshot format tests/integration/schema/production.tsv is written in."""

    def test_one_sorted_line_per_object(self):
        fk = ForeignKey(('id',), 'others', ('id',), 'CASCADE', 'RESTRICT')
        schema = Schema(tables={'things': _table(foreign_keys={fk})}, views={'thing_names'})
        self.assertEqual(
            snapshot_lines(schema),
            [
                'C\tthings\tid\tint(11)\tNO\t<none>\tauto_increment\t<none>',
                'C\tthings\tname\tvarchar(255)\tNO\t<none>\t\tutf8mb4_general_ci',
                'C\tthings\tnote\ttext\tYES\tNULL\t\tutf8mb4_general_ci',
                'F\tthings\tid\tothers\tid\tCASCADE\tRESTRICT',
                'I\tthings\tPRIMARY\t1\tid\tBTREE',
                'I\tthings\tidx_name\t0\tname\tBTREE',
                'T\tthings\tInnoDB\tutf8mb4_general_ci',
                'V\tthing_names',
            ],
        )


class ReadSchemaTest(unittest.TestCase):
    """read_schema() keeps SQL NULL apart from the string 'NULL' and accepts tuple rows."""

    def test_a_null_default_and_a_null_string_default_differ(self):
        cursor = mock.MagicMock()
        cursor.fetchall.side_effect = [
            [('t', 'BASE TABLE', 'InnoDB', 'utf8mb4_general_ci')],
            [('t', 'a', 'text', 'YES', None, '', None), ('t', 'b', 'text', 'YES', 'NULL', '', None)],
            [],
            [],
            [],
        ]
        columns = schema_reconcile.read_schema(cursor, 'db').tables['t'].columns
        self.assertEqual((columns['a'].default, columns['b'].default), ('<none>', 'NULL'))


if __name__ == '__main__':
    unittest.main()
