"""The repair of word-prefixed release folders in the label tree, on production names."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

import pytest
from mutagen.id3 import ID3, TXXX
from mutagen.mp4 import MP4FreeForm, MP4Tags

pytestmark = pytest.mark.mock_base('Cache')

from services.common.import_queue import ImportQueue  # noqa: E402
from services.importer.label_tree_prefix_repair import (  # noqa: E402
    apply_plan,
    backup_where,
    classify,
    drop_catalogue_tag,
    label_tree_folders,
    plan,
    rollback,
    summarize,
)

MINUS_MILITIA = (
    'Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-SINGLE-WEB-2026-UTNG'
)
WORD_PREFIXED = 'Official_Hardbass_2026_Anthem - ' + MINUS_MILITIA
FRENCHCORE = 'I_Am_Frenchcore_05 - Amnesia_and_Radium_-_Hard_Plastic-()-WEB-2020'
RULES = {'scan': 'Scantraxx'}


def _touch(path):
    """Creates an empty file."""
    with open(path, 'w', encoding='utf-8'):
        pass


class ClassifyTest(unittest.TestCase):
    def test_a_festival_anthem_prefix_is_renamed_to_the_bare_name(self):
        entry = classify('B2S', WORD_PREFIXED, RULES)

        self.assertEqual('rename', entry.verdict)
        self.assertEqual(MINUS_MILITIA, entry.new)
        self.assertEqual('Official_Hardbass_2026_Anthem', entry.prefix)
        self.assertEqual('B2S/' + MINUS_MILITIA, entry.new_path)

    def test_a_remix_marker_prefix_is_renamed(self):
        entry = classify('Texcore', 'Equal2_Remix - Lil_Texas_-_Rip_City_(Equal2_Remix)-WEB-2026', RULES)

        self.assertEqual('Lil_Texas_-_Rip_City_(Equal2_Remix)-WEB-2026', entry.new)

    def test_a_real_catalogue_number_is_left_alone(self):
        self.assertIsNone(classify('Disobey Records', 'DSB_REC_028 - BreakStyle_-_Fvck_Sapos-()-WEB-2020', RULES))
        self.assertIsNone(classify('Redemption Records', 'RR_ALBUM_001B - Radical_Redemption-(RR_ALBUM_001B)', RULES))

    def test_an_empty_prefix_is_fine_in_the_label_tree(self):
        self.assertIsNone(classify('B2S', ' - Guizcore_-_Coffee_Time-WEB-FLAC-2026', RULES))

    def test_a_label_code_without_a_digit_is_left_alone(self):
        self.assertIsNone(
            classify('Filthy Face Records', 'FILTHY - Emerged_-_The_Light_(Original_Mix)-WEB-2023', RULES)
        )

    def test_a_name_without_a_prefix_is_left_alone(self):
        self.assertIsNone(classify('B2S', MINUS_MILITIA, RULES))

    def test_a_refused_prefix_the_old_renamer_cannot_have_written_is_ambiguous(self):
        entry = classify('I Am Frenchcore', FRENCHCORE, RULES)

        self.assertEqual('ambiguous', entry.verdict)
        self.assertIsNone(entry.new)
        self.assertIn('cased-words', entry.reason)

    def test_a_refused_prefix_a_rule_routes_is_ambiguous(self):
        name = 'Scan_Anthem_123 - Artist_-_Title_(Scan_Anthem_123)-WEB-2024'

        entry = classify('Scantraxx', name, {'scananthem': 'Scantraxx'})

        self.assertEqual('ambiguous', entry.verdict)
        self.assertIn('Scantraxx', entry.reason)

    def test_a_rest_that_carries_a_catalogue_number_gets_it_in_front(self):
        entry = classify('Label', 'Official_2024_Anthem - Artist_-_Title_(Official_2024_Anthem)-(BRUT016D)-WEB', RULES)

        # The old Renamer took the last group with a digit, which is BRUT016D, not the anthem.
        self.assertEqual('ambiguous', entry.verdict)
        entry = classify('Label', 'Official_2024_Anthem - Artist_-_Title-(BRUT016D)-(Official_2024_Anthem)-WEB', RULES)

        self.assertEqual('BRUT016D - Artist_-_Title-(BRUT016D)-(Official_2024_Anthem)-WEB', entry.new)

    def test_a_rest_with_a_space_keeps_an_empty_prefix(self):
        entry = classify('Label', 'Live_2024_Anthem - Artist - Title_(Live_2024_Anthem)', RULES)

        self.assertEqual(' - Artist - Title_(Live_2024_Anthem)', entry.new)


class PlanTest(unittest.TestCase):
    def test_a_rename_onto_a_name_already_in_the_label_folder_is_refused(self):
        planned = plan([('B2S', WORD_PREFIXED), ('B2S', MINUS_MILITIA)], RULES)

        self.assertEqual(1, len(planned))
        self.assertEqual('skip', planned[0].verdict)
        self.assertTrue(planned[0].reason.startswith('target exists'))

    def test_the_same_name_under_another_label_is_no_conflict(self):
        planned = plan([('B2S', WORD_PREFIXED), ('Other', MINUS_MILITIA)], RULES)

        self.assertEqual(['rename'], [entry.verdict for entry in planned])

    def test_the_summary_counts_each_kind(self):
        planned = plan([('B2S', WORD_PREFIXED), ('I Am Frenchcore', FRENCHCORE), ('X', 'HA037 - Y-(HA037)')], RULES)

        self.assertEqual(
            {'release_folders': 3, 'word_prefixed': 2, 'renameable': 1, 'ambiguous': 1, 'target_exists': 0},
            summarize(planned, 3),
        )

    def test_the_backup_filter_selects_only_the_renamed_folders(self):
        planned = plan([('B2S', WORD_PREFIXED), ('I Am Frenchcore', FRENCHCORE), ("Dj's", WORD_PREFIXED)], RULES)

        where = backup_where(planned, '/mnt/music/EPs', 'file_path')

        self.assertIn(f"'/mnt/music/EPs/B2S/{WORD_PREFIXED}/'", where)
        self.assertIn("'/mnt/music/EPs/Dj''s/", where)
        self.assertNotIn('Frenchcore', where)
        self.assertEqual('1 = 0', backup_where([], '/mnt/music/EPs', 'file_path'))


class LabelTreeFoldersTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for folder in ('B2S/' + WORD_PREFIXED, 'import-queue/' + WORD_PREFIXED, '__Free&None/' + WORD_PREFIXED):
            os.makedirs(os.path.join(self.root, folder))
        _touch(os.path.join(self.root, 'B2S', 'cover.jpg'))
        _touch(os.path.join(self.root, 'stray.mp3'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_release_folders_under_label_folders_are_listed(self):
        queue = ImportQueue(os.path.join(self.root, 'import-queue'))

        self.assertEqual([('B2S', WORD_PREFIXED)], label_tree_folders(self.root, queue))


def _connection():
    cursor = MagicMock()
    cursor.rowcount = 2
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection, cursor


class ApplyAndRollbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, 'B2S', WORD_PREFIXED))
        _touch(os.path.join(self.root, 'B2S', WORD_PREFIXED, '01-track.mp3'))
        _touch(os.path.join(self.root, 'B2S', WORD_PREFIXED, 'release.nfo'))
        self.log = os.path.join(self.root, 'renames.jsonl')

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_renames_rewrites_paths_clears_the_tag_and_logs(self):
        connection, cursor = _connection()
        notified, dropped = [], []
        planned = plan([('B2S', WORD_PREFIXED)], RULES)

        result = apply_plan(
            planned,
            self.root,
            self.log,
            connection,
            notify=notified.append,
            drop=lambda path, prefix: dropped.append((os.path.basename(path), prefix)) or True,
        )

        self.assertTrue(os.path.isdir(os.path.join(self.root, 'B2S', MINUS_MILITIA)))
        self.assertFalse(os.path.exists(os.path.join(self.root, 'B2S', WORD_PREFIXED)))
        self.assertEqual(
            {'renamed': 1, 'skipped': 0, 'media_rows': 2, 'tagger_rows': 2},
            {key: result[key] for key in ('renamed', 'skipped', 'media_rows', 'tagger_rows')},
        )
        self.assertEqual([('01-track.mp3', 'Official_Hardbass_2026_Anthem')], dropped)
        media_sql, media_args = cursor.execute.call_args_list[0].args
        self.assertIn('UPDATE library_media_files', media_sql)
        self.assertIn('file_path_hash = SHA2', media_sql)
        old_dir = os.path.join(self.root, 'B2S', WORD_PREFIXED) + '/'
        new_dir = os.path.join(self.root, 'B2S', MINUS_MILITIA) + '/'
        self.assertEqual((new_dir, old_dir, new_dir, old_dir, old_dir, old_dir), media_args)
        self.assertIn('UPDATE tagger_processed_files', cursor.execute.call_args_list[1].args[0])
        connection.commit.assert_called_once()
        self.assertEqual(1, len(notified))
        with open(self.log, encoding='utf-8') as handle:
            record = json.loads(handle.readline())
        self.assertEqual(('B2S', WORD_PREFIXED, MINUS_MILITIA), (record['label'], record['old'], record['new']))

    def test_a_second_plan_after_apply_finds_nothing(self):
        connection, _ = _connection()
        apply_plan(plan([('B2S', WORD_PREFIXED)], RULES), self.root, self.log, connection, drop=lambda *_: False)

        queue = ImportQueue(os.path.join(self.root, 'import-queue'))
        self.assertEqual([], plan(label_tree_folders(self.root, queue), RULES))

    def test_a_failed_commit_renames_the_folder_back(self):
        connection, _ = _connection()
        connection.commit.side_effect = RuntimeError('gone')

        with self.assertRaises(RuntimeError):
            apply_plan(plan([('B2S', WORD_PREFIXED)], RULES), self.root, self.log, connection, drop=lambda *_: False)

        self.assertTrue(os.path.isdir(os.path.join(self.root, 'B2S', WORD_PREFIXED)))

    def test_a_failed_rewrite_leaves_the_folder_where_it_was(self):
        connection, cursor = _connection()
        cursor.execute.side_effect = RuntimeError('lock wait timeout')

        with self.assertRaises(RuntimeError):
            apply_plan(plan([('B2S', WORD_PREFIXED)], RULES), self.root, self.log, connection, drop=lambda *_: False)

        connection.rollback.assert_called_once()
        self.assertTrue(os.path.isdir(os.path.join(self.root, 'B2S', WORD_PREFIXED)))

    def test_rollback_puts_the_name_and_the_paths_back(self):
        connection, cursor = _connection()
        apply_plan(plan([('B2S', WORD_PREFIXED)], RULES), self.root, self.log, connection, drop=lambda *_: False)
        cursor.execute.reset_mock()

        result = rollback(self.log, self.root, connection)

        self.assertEqual(1, result['restored'])
        self.assertTrue(os.path.isdir(os.path.join(self.root, 'B2S', WORD_PREFIXED)))
        new_dir = os.path.join(self.root, 'B2S', MINUS_MILITIA) + '/'
        self.assertEqual(new_dir, cursor.execute.call_args_list[0].args[1][1])


class _Audio:
    """A stand-in for a mutagen file: real tag objects, a counted save."""

    def __init__(self, tags):
        self.tags = tags
        self.saves = 0

    def save(self):
        self.saves += 1


class DropCatalogueTagTest(unittest.TestCase):
    def test_an_id3_frame_holding_the_word_is_removed(self):
        tags = ID3()
        tags.add(TXXX(encoding=3, desc='CATALOGNUMBER', text=['Official_Hardbass_2026_Anthem']))
        audio = _Audio(tags)

        self.assertTrue(drop_catalogue_tag('x.mp3', 'Official_Hardbass_2026_Anthem', open_file=lambda _: audio))

        self.assertNotIn('TXXX:CATALOGNUMBER', tags)
        self.assertEqual(1, audio.saves)

    def test_a_different_catalogue_number_stays(self):
        tags = ID3()
        tags.add(TXXX(encoding=3, desc='CATALOGNUMBER', text=['CAT1441025']))
        audio = _Audio(tags)

        self.assertFalse(drop_catalogue_tag('x.mp3', 'Official_Akelarre_2025_Anthem', open_file=lambda _: audio))

        self.assertIn('TXXX:CATALOGNUMBER', tags)
        self.assertEqual(0, audio.saves)

    def test_a_vorbis_comment_holding_the_word_is_removed_and_the_label_stays(self):
        tags = {'catalognumber': ['Official_Akelarre_2025_Anthem'], 'label': ['Magistrates Music']}
        audio = _Audio(tags)

        self.assertTrue(drop_catalogue_tag('x.flac', 'Official_Akelarre_2025_Anthem', open_file=lambda _: audio))

        self.assertEqual({'label': ['Magistrates Music']}, tags)

    def test_an_mp4_freeform_atom_holding_the_word_is_removed(self):
        tags = MP4Tags()
        tags['----:com.apple.iTunes:CATALOGNUMBER'] = [MP4FreeForm(b'Zaandam_Anthem_2026')]
        audio = _Audio(tags)

        self.assertTrue(drop_catalogue_tag('x.m4a', 'Zaandam_Anthem_2026', open_file=lambda _: audio))

        self.assertEqual([], list(tags.keys()))

    def test_a_file_without_tags_is_left_alone(self):
        self.assertFalse(drop_catalogue_tag('x.mp3', 'X_2024_Anthem', open_file=lambda _: _Audio(None)))
