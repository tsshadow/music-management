"""Coverage for services/tagger/tagger.py: folder walking, dispatch and auto-detection."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.tagger import tagger as tagger_module
from services.tagger.constants import SongTypeEnum
from services.tagger.tagger import Tagger, TagSingleFile


class TaggerTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.music = self.root / 'music'
        self.eps = self.root / 'eps'
        self.music.mkdir()
        self.eps.mkdir()
        self.settings = MagicMock(music_folder_path=str(self.music), eps_folder_path=str(self.eps))
        patches = [
            patch.object(tagger_module, 's', self.settings),
            patch.object(tagger_module, 'processed_files_helper', MagicMock()),
            patch.object(tagger_module, 'broken_song_helper', MagicMock()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.processed = tagger_module.processed_files_helper
        self.processed.needs_processing.return_value = True
        self.tagger = Tagger()
        self.tagger.parallel = False

    def make_song(self, folder: Path, name='a.mp3'):
        folder.mkdir(parents=True, exist_ok=True)
        song = folder / name
        song.write_text('audio')
        return song


class ImportFolderTest(TaggerTestCase):
    """The import folder sits inside the EPs root and must never be tagged as a label.

    `import_folder_path` is `/mnt/music/EPs/__TODO` and `eps_folder_path` is `/mnt/music/EPs`, so
    every folder scan over the EPs root walks straight into the release queue. LabelSong takes the
    publisher from the grandparent folder name (`LabelSong.py:22-23`), so a file tagged while it is
    still waiting there gets `publisher = __TODO` written into it -- and that is what happened to
    part of the library before the underscore guard was added. Five of 25 files sampled on
    production on 2026-08-19 still carry it.

    The guard is one condition in one expression and reads like a style choice. These tests are what
    say it is not.
    """

    def test_an_underscore_folder_is_not_treated_as_a_label(self):
        self.make_song(self.eps / '__TODO' / 'Some Release')

        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_label_folders()

        types = [call.args[1] for call in parse_folder.call_args_list]
        self.assertEqual([SongTypeEnum.GENERIC], types)

    def test_an_ordinary_label_folder_still_is(self):
        self.make_song(self.eps / 'Roughstate' / 'Some Release')

        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_label_folders()

        types = [call.args[1] for call in parse_folder.call_args_list]
        self.assertEqual([SongTypeEnum.LABEL], types)

    def test_the_single_file_path_agrees_with_the_folder_scan(self):
        """Two independent decisions, one rule. They drifted apart once already."""
        song = self.make_song(self.eps / '__TODO' / 'Some Release')

        with (
            patch.object(tagger_module.Tagger, 'parse_song') as parse_song,
            patch.object(tagger_module, 'settings', self.settings, create=True),
        ):
            tagger_module.TagSingleFile(song)

        self.assertEqual(SongTypeEnum.GENERIC, parse_song.call_args.args[1])


class RunTest(TaggerTestCase):
    def steps(self):
        return {
            name: patch.object(self.tagger, name)
            for name in ('_parse_label_folders', '_parse_channel_folders', '_parse_generic_folders')
        }

    def test_a_full_run_covers_labels_all_three_platforms_and_the_generic_folders(self):
        with (
            patch.object(self.tagger, '_parse_label_folders') as labels,
            patch.object(self.tagger, '_parse_channel_folders') as channels,
            patch.object(self.tagger, '_parse_generic_folders') as generic,
        ):
            self.tagger.run()
        labels.assert_called_once()
        generic.assert_called_once()
        self.assertEqual([call.args[0] for call in channels.call_args_list], ['Soundcloud', 'Youtube', 'Telegram'])

    def test_each_source_can_be_switched_off(self):
        with (
            patch.object(self.tagger, '_parse_label_folders') as labels,
            patch.object(self.tagger, '_parse_channel_folders') as channels,
            patch.object(self.tagger, '_parse_generic_folders') as generic,
        ):
            self.tagger.run(
                parse_labels=False,
                parse_soundcloud=False,
                parse_youtube=False,
                parse_generic=False,
                parse_telegram=False,
            )
        labels.assert_not_called()
        channels.assert_not_called()
        generic.assert_not_called()

    def test_a_stop_request_from_the_first_step_skips_the_rest(self):
        def stop_immediately():
            self.tagger.stop_requested = True

        with (
            patch.object(self.tagger, '_parse_label_folders', side_effect=stop_immediately),
            patch.object(self.tagger, '_parse_channel_folders') as channels,
            patch.object(self.tagger, '_parse_generic_folders') as generic,
        ):
            self.tagger.run()
        channels.assert_not_called()
        generic.assert_not_called()

    def test_a_run_clears_a_stop_request_left_over_from_the_previous_one(self):
        self.tagger.stop_requested = True
        with (
            patch.object(self.tagger, '_parse_label_folders') as labels,
            patch.object(self.tagger, '_parse_channel_folders'),
            patch.object(self.tagger, '_parse_generic_folders'),
        ):
            self.tagger.run()
        labels.assert_called_once()

    def test_a_run_refreshes_the_rule_caches_first(self):
        # Without this the run would tag with the rules it read at import, so a rule
        # changed today would look like it had no effect at all.
        with (
            patch.object(tagger_module, 'reload_rule_caches') as reload_rule_caches,
            patch.object(self.tagger, '_parse_label_folders'),
            patch.object(self.tagger, '_parse_channel_folders'),
            patch.object(self.tagger, '_parse_generic_folders'),
        ):
            self.tagger.run()
        reload_rule_caches.assert_called_once()

    def test_a_run_asks_lms_to_pick_up_what_changed(self):
        with (
            patch.object(self.tagger, '_parse_label_folders'),
            patch.object(self.tagger, '_parse_channel_folders'),
            patch.object(self.tagger, '_parse_generic_folders'),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger.run()
        trigger.trigger.assert_called_once()


class FolderWalkTest(TaggerTestCase):
    def test_every_label_folder_is_parsed_as_a_label(self):
        (self.eps / 'Scantraxx').mkdir()
        with patch.object(self.tagger, 'parse_folder') as parse_folder, patch('builtins.print'):
            self.tagger._parse_label_folders()
        self.assertEqual(parse_folder.call_args.args[1], SongTypeEnum.LABEL)

    def test_an_underscore_prefixed_label_folder_is_treated_as_generic(self):
        (self.eps / '_Misc').mkdir()
        with patch.object(self.tagger, 'parse_folder') as parse_folder, patch('builtins.print'):
            self.tagger._parse_label_folders()
        self.assertEqual(parse_folder.call_args.args[1], SongTypeEnum.GENERIC)

    def test_a_stop_request_ends_the_label_walk(self):
        for name in ('A', 'B'):
            (self.eps / name).mkdir()
        self.tagger.stop_requested = True
        with patch.object(self.tagger, 'parse_folder') as parse_folder, patch('builtins.print'):
            self.tagger._parse_label_folders()
        parse_folder.assert_not_called()

    def test_every_channel_folder_of_a_platform_is_parsed(self):
        (self.music / 'Soundcloud' / 'artist').mkdir(parents=True)
        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_channel_folders('Soundcloud', SongTypeEnum.SOUNDCLOUD)
        self.assertEqual(parse_folder.call_args.args[1], SongTypeEnum.SOUNDCLOUD)

    def test_a_platform_folder_that_does_not_exist_is_skipped(self):
        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_channel_folders('Youtube', SongTypeEnum.YOUTUBE)
        parse_folder.assert_not_called()

    def test_a_stop_request_ends_the_channel_walk(self):
        (self.music / 'Soundcloud' / 'artist').mkdir(parents=True)
        self.tagger.stop_requested = True
        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_channel_folders('Soundcloud', SongTypeEnum.SOUNDCLOUD)
        parse_folder.assert_not_called()

    def test_every_generic_root_that_exists_is_handed_to_parse_folder(self):
        (self.music / 'Livesets' / 'Defqon').mkdir(parents=True)
        (self.music / 'Podcasts' / 'Show').mkdir(parents=True)
        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_generic_folders()
        self.assertEqual(
            [call.args[0] for call in parse_folder.call_args_list], [self.music / 'Livesets', self.music / 'Podcasts']
        )
        self.assertEqual(parse_folder.call_args.args[1], SongTypeEnum.GENERIC)

    def test_a_file_loose_in_a_generic_root_is_parsed_too(self):
        self.make_song(self.music / 'Warm Up Mixes', 'Korsakoff at Pussy Lounge 2019.mp3')
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger._parse_generic_folders()
        self.assertEqual(
            [call.args[0].name for call in try_parse.call_args_list], ['Korsakoff at Pussy Lounge 2019.mp3']
        )

    def test_a_missing_generic_folder_is_skipped(self):
        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_generic_folders()
        parse_folder.assert_not_called()

    def test_a_stop_request_ends_the_generic_walk(self):
        (self.music / 'Livesets' / 'Defqon').mkdir(parents=True)
        self.tagger.stop_requested = True
        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_generic_folders()
        parse_folder.assert_not_called()


class ParseFolderTest(TaggerTestCase):
    def test_a_single_file_is_parsed_directly(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger.parse_folder(song, SongTypeEnum.SOUNDCLOUD)
        try_parse.assert_called_once()

    def test_only_the_enabled_extensions_are_picked_up(self):
        folder = self.music / 'Soundcloud' / 'artist'
        for name in ('a.mp3', 'b.flac', 'c.m4a', 'd.wav', 'e.aac', 'cover.jpg'):
            self.make_song(folder, name)
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        self.assertEqual(try_parse.call_count, 3)

    def test_synology_metadata_folders_are_skipped(self):
        folder = self.music / 'Soundcloud' / '@eaDir'
        self.make_song(folder)
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        try_parse.assert_not_called()

    def test_subfolders_are_walked_recursively(self):
        folder = self.music / 'Soundcloud' / 'artist'
        self.make_song(folder / 'album')
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        try_parse.assert_called_once()

    def test_underscore_prefixed_subfolders_are_not_walked(self):
        folder = self.music / 'Soundcloud' / 'artist'
        self.make_song(folder / '_private')
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        try_parse.assert_not_called()

    def test_a_stop_request_prevents_the_folder_from_being_touched(self):
        folder = self.music / 'Soundcloud' / 'artist'
        self.make_song(folder)
        self.tagger.stop_requested = True
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        try_parse.assert_not_called()

    def test_an_unreadable_folder_is_logged_rather_than_raised(self):
        folder = self.music / 'Soundcloud' / 'artist'
        folder.mkdir(parents=True)
        with patch.object(Path, 'glob', side_effect=PermissionError('denied')), self.assertLogs(level='ERROR'):
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)

    def test_the_parallel_path_hands_every_file_to_a_worker(self):
        folder = self.music / 'Soundcloud' / 'artist'
        for name in ('a.mp3', 'b.mp3'):
            self.make_song(folder, name)
        self.tagger.parallel = True
        with patch.object(Tagger, '_parse_worker', return_value=('x', 'OK')) as worker:
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        self.assertEqual(worker.call_count, 2)


class TryParseTest(TaggerTestCase):
    def test_a_file_that_did_not_change_is_skipped(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        self.processed.needs_processing.return_value = False
        with patch.object(Tagger, 'parse_song') as parse_song:
            self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)
        parse_song.assert_not_called()

    def test_a_parsed_file_is_marked_as_processed(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song'):
            self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)
        self.processed.mark_processed.assert_called_once()

    def test_an_unreadable_file_is_recorded_as_broken(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song', side_effect=PermissionError('denied')), self.assertLogs(level='ERROR'):
            self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)
        tagger_module.broken_song_helper.add.assert_called_once()
        self.processed.mark_processed.assert_not_called()

    def test_an_unexpected_failure_is_logged_and_the_file_left_unmarked(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song', side_effect=RuntimeError('boom')), self.assertLogs(level='ERROR'):
            self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)
        self.processed.mark_processed.assert_not_called()

    def test_an_interrupt_stops_the_process(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song', side_effect=KeyboardInterrupt), self.assertRaises(SystemExit):
            self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)


class ParseSongTest(TaggerTestCase):
    def dispatch(self, song_type, class_name):
        with patch.object(tagger_module, class_name) as song_class:
            Tagger.parse_song(Path('/music/a.mp3'), song_type)
        song_class.return_value.parse.assert_called_once()
        return song_class

    def test_a_label_song_is_dispatched_to_labelsong(self):
        self.dispatch(SongTypeEnum.LABEL, 'LabelSong')

    def test_a_youtube_song_is_dispatched_to_youtubesong(self):
        self.dispatch(SongTypeEnum.YOUTUBE, 'YoutubeSong')

    def test_a_soundcloud_song_is_dispatched_to_soundcloudsong(self):
        self.dispatch(SongTypeEnum.SOUNDCLOUD, 'SoundcloudSong')

    def test_a_telegram_song_is_dispatched_to_telegramsong(self):
        self.dispatch(SongTypeEnum.TELEGRAM, 'TelegramSong')

    def test_a_generic_song_is_dispatched_to_genericsong(self):
        self.dispatch(SongTypeEnum.GENERIC, 'GenericSong')

    def test_manual_tags_are_written_and_saved(self):
        with patch.object(tagger_module, 'LabelSong') as song_class:
            Tagger.parse_song(Path('/music/a.mp3'), SongTypeEnum.LABEL, {'artist': 'Angerfist'})
        song = song_class.return_value
        song.tag_collection.add.assert_called_once_with('artist', 'Angerfist')
        song.save_file.assert_called_once()

    def test_without_manual_tags_nothing_is_written_back(self):
        with patch.object(tagger_module, 'LabelSong') as song_class:
            Tagger.parse_song(Path('/music/a.mp3'), SongTypeEnum.LABEL)
        song_class.return_value.save_file.assert_not_called()


class ParseWorkerTest(TaggerTestCase):
    def test_an_unchanged_file_is_reported_as_skipped(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        self.processed.needs_processing.return_value = False
        self.assertEqual(Tagger._parse_worker(str(song), 'SOUNDCLOUD')[1], 'SKIPPED')

    def test_a_parsed_file_is_reported_as_ok_and_marked(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song'):
            self.assertEqual(Tagger._parse_worker(str(song), 'SOUNDCLOUD')[1], 'OK')
        self.processed.mark_processed.assert_called_once()

    def test_a_failure_is_reported_back_instead_of_raised(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song', side_effect=RuntimeError('boom')):
            self.assertIn('RuntimeError', Tagger._parse_worker(str(song), 'SOUNDCLOUD')[1])

    def test_a_failure_is_logged_and_not_only_returned(self):
        """The parallel path is the one production runs, and `parse_folder` throws the
        worker's return value away. Without this line a file that failed every round is
        indistinguishable from one that was tagged: the podcast tag went missing for
        weeks with not one error in the log."""
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with (
            patch.object(Tagger, 'parse_song', side_effect=RuntimeError('boom')),
            self.assertLogs(level='ERROR') as logs,
        ):
            Tagger._parse_worker(str(song), 'SOUNDCLOUD')
        self.assertIn('boom', '\n'.join(logs.output))
        self.assertIn(str(song), '\n'.join(logs.output))

    def test_a_file_that_failed_is_not_marked_as_processed(self):
        """So the next round reads it again rather than trusting a round that wrote
        nothing."""
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song', side_effect=RuntimeError('boom')), self.assertLogs(level='ERROR'):
            Tagger._parse_worker(str(song), 'SOUNDCLOUD')
        self.processed.mark_processed.assert_not_called()


class TagSingleFileTest(TaggerTestCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(tagger_module, 'Settings', return_value=self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def detect(self, path):
        with patch.object(Tagger, 'parse_song') as parse_song, patch('builtins.print'):
            TagSingleFile(str(path))
        return parse_song.call_args.args[1]

    def test_a_file_under_a_label_folder_is_detected_as_a_label_song(self):
        song = self.make_song(self.eps / 'Scantraxx' / 'SCAN123')
        self.assertEqual(self.detect(song), SongTypeEnum.LABEL)

    def test_a_file_under_an_underscore_label_folder_is_generic(self):
        song = self.make_song(self.eps / '_Misc')
        self.assertEqual(self.detect(song), SongTypeEnum.GENERIC)

    def test_a_soundcloud_file_is_detected(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        self.assertEqual(self.detect(song), SongTypeEnum.SOUNDCLOUD)

    def test_a_youtube_file_is_detected(self):
        song = self.make_song(self.music / 'Youtube' / 'channel')
        self.assertEqual(self.detect(song), SongTypeEnum.YOUTUBE)

    def test_a_telegram_file_is_detected(self):
        song = self.make_song(self.music / 'Telegram' / 'chat')
        self.assertEqual(self.detect(song), SongTypeEnum.TELEGRAM)

    def test_a_liveset_is_detected_as_generic(self):
        song = self.make_song(self.music / 'Livesets' / 'Defqon')
        self.assertEqual(self.detect(song), SongTypeEnum.GENERIC)

    def test_a_file_somewhere_else_falls_back_to_generic(self):
        song = self.make_song(self.root / 'elsewhere')
        self.assertEqual(self.detect(song), SongTypeEnum.GENERIC)

    def test_a_path_object_is_accepted_as_well_as_a_string(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song') as parse_song, patch('builtins.print'):
            TagSingleFile(song)
        self.assertEqual(parse_song.call_args.args[1], SongTypeEnum.SOUNDCLOUD)

    def test_a_tagged_file_is_marked_as_processed(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song'), patch('builtins.print'):
            TagSingleFile(str(song))
        self.processed.mark_processed.assert_called_once()

    def test_a_file_that_disappeared_after_tagging_is_only_logged(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        path = str(song)
        song.unlink()
        with patch.object(Tagger, 'parse_song'), patch('builtins.print'), self.assertLogs(level='ERROR'):
            TagSingleFile(path)
        self.processed.mark_processed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
