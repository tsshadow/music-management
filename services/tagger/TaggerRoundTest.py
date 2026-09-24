"""What a tagging round shares across its files: one connection per thread, one rule stack, one summary line.

Every helper the tagger calls per file used to open its own database connection, and every
song rebuilt its whole rule stack -- InferArtistFromTitleRule turning 37k artist names into
a set twice and reading two lists from the database. See bug report 063.
"""

import logging
import threading
from unittest.mock import MagicMock, patch

from services.common.Helpers import RoundScope
from services.tagger import tagger as tagger_module
from services.tagger.Song import rule_stack
from services.tagger.TaggerTest import TaggerTestCase


class CountingOpener:
    """A connection factory standing in for pymysql.connect; records which thread opened what."""

    def __init__(self):
        self.opened = []
        self._lock = threading.Lock()

    def __call__(self):
        connection = MagicMock()
        with self._lock:
            self.opened.append((connection, threading.get_ident()))
        return connection


class RoundTestCase(TaggerTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(tagger_module, 'Settings', return_value=self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.opener = CountingOpener()

    def queue(self, count):
        songs = [self.make_song(self.music / 'Livesets', f'{i}.mp3') for i in range(count)]
        self.processed.pending_paths.side_effect = [[str(song) for song in songs], []]
        return songs

    def per_file_helpers(self, *_args, **_kwargs):
        """What parse_song does per file: the rule stack, and four helpers that each connect."""
        rule_stack.rules_for(rule_stack.GENERIC)
        for _ in range(4):
            RoundScope.connect(self.opener).close()
        return MagicMock(saved=False)


class OneConnectionPerRoundTest(RoundTestCase):
    def test_a_serial_round_opens_one_connection_for_n_files(self):
        self.queue(10)
        with patch.object(tagger_module.Tagger, 'parse_song', side_effect=self.per_file_helpers):
            self.tagger.run(walk=False)
        self.assertEqual(len(self.opener.opened), 1)
        connection, _ = self.opener.opened[0]
        connection.close.assert_called_once()

    def test_a_parallel_round_opens_at_most_one_connection_per_worker(self):
        self.tagger.parallel = True
        self.queue(60)
        with (
            patch.object(tagger_module, 'TAGGER_BATCH_PAUSE', 0),
            patch.object(tagger_module.Tagger, 'parse_song', side_effect=self.per_file_helpers),
        ):
            self.tagger.run(walk=False)
        self.assertGreaterEqual(len(self.opener.opened), 1)
        self.assertLessEqual(len(self.opener.opened), tagger_module.TAGGER_WORKERS)
        # Every worker keeps its own; none is shared between threads, and all are closed.
        self.assertEqual(len({thread for _, thread in self.opener.opened}), len(self.opener.opened))
        for connection, _ in self.opener.opened:
            connection.close.assert_called_once()

    def test_the_round_pool_is_gone_after_the_round(self):
        self.tagger.parallel = True
        self.queue(3)
        with (
            patch.object(tagger_module, 'TAGGER_BATCH_PAUSE', 0),
            patch.object(tagger_module.Tagger, 'parse_song', side_effect=self.per_file_helpers),
        ):
            self.tagger.run(walk=False)
        self.assertIsNone(self.tagger._pool)
        self.assertIsNone(RoundScope.current())


class OneRuleStackPerRoundTest(RoundTestCase):
    def test_the_rule_stack_is_built_once_per_round_not_per_file(self):
        self.queue(10)
        builder = MagicMock(return_value=[])
        with (
            patch.dict(rule_stack.BUILDERS, {rule_stack.GENERIC: builder}),
            patch.object(tagger_module.Tagger, 'parse_song', side_effect=self.per_file_helpers),
        ):
            self.tagger.run(walk=False)
            self.assertEqual(builder.call_count, 1)
            self.processed.pending_paths.side_effect = [[str(self.music / 'Livesets' / '0.mp3')], []]
            self.tagger.run(walk=False)
        # A new round reads the rules again, so a decision made in between is honoured.
        self.assertEqual(builder.call_count, 2)

    def test_the_parallel_workers_share_the_rounds_rule_stack(self):
        self.tagger.parallel = True
        self.queue(40)
        builder = MagicMock(return_value=[])
        with (
            patch.object(tagger_module, 'TAGGER_BATCH_PAUSE', 0),
            patch.dict(rule_stack.BUILDERS, {rule_stack.GENERIC: builder}),
            patch.object(tagger_module.Tagger, 'parse_song', side_effect=self.per_file_helpers),
        ):
            self.tagger.run(walk=False)
        self.assertEqual(builder.call_count, 1)


class RoundSummaryTest(RoundTestCase):
    def test_a_round_that_tagged_files_logs_one_summary_line(self):
        self.queue(3)
        written = iter([True, False, False])

        def parse(*_args, **_kwargs):
            self.per_file_helpers()
            return MagicMock(saved=next(written))

        with (
            patch.object(tagger_module.Tagger, 'parse_song', side_effect=parse),
            self.assertLogs(level='INFO') as logs,
        ):
            self.tagger.run(walk=False)
        summaries = [record for record in logs.records if record.getMessage().startswith('Tagging round:')]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].levelno, logging.INFO)
        message = summaries[0].getMessage()
        self.assertIn('3 file(s) tagged (1 written, 0 up to date)', message)
        self.assertIn('ms/file', message)
        self.assertIn('1 database connection(s) opened', message)

    def test_the_parallel_path_counts_what_its_workers_did(self):
        self.tagger.parallel = True
        self.queue(4)
        statuses = iter(['SAVED', 'OK', 'SKIPPED', 'OK'])
        lock = threading.Lock()

        def worker(file, *_args):
            with lock:
                return (file, next(statuses))

        with (
            patch.object(tagger_module, 'TAGGER_BATCH_PAUSE', 0),
            patch.object(tagger_module.Tagger, '_parse_worker', side_effect=worker),
            self.assertLogs(level='INFO') as logs,
        ):
            self.tagger.run(walk=False)
        summary = next(line for line in logs.output if 'Tagging round:' in line)
        self.assertIn('3 file(s) tagged (1 written, 1 up to date)', summary)

    def test_an_idle_round_adds_no_info_line(self):
        """The loop runs every five minutes and most rounds find nothing; an INFO line
        each would be an events-table row for nothing."""
        with self.assertLogs(level='DEBUG') as logs:
            self.tagger.run(walk=False)
        summaries = [record for record in logs.records if record.getMessage().startswith('Tagging round:')]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].levelno, logging.DEBUG)
