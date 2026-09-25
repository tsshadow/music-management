"""Coverage for services/tagger/tagger.py: folder walking, dispatch and auto-detection."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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
            # parse_song asks the archive what the download knew. Stubbed for the whole
            # suite so no dispatch test reaches a database, and set per test where the
            # lookup itself is what is under test.
            patch.object(tagger_module, 'download_info', MagicMock(**{'stored_info.return_value': None})),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.processed = tagger_module.processed_files_helper
        self.processed.needs_processing.return_value = True
        # An empty queue by default: a MagicMock is truthy and would keep the pending
        # pass paging for ever. One reason, so the pass asks for pages at all.
        self.processed.pending_paths.return_value = []
        self.processed.pending_reasons.return_value = ['genre_decision']
        self.processed.queue_new_library_files.return_value = 0
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

    def test_a_missing_eps_root_is_skipped_rather_than_thrown(self):
        """A share that has not mounted yet must not take the tagger loop with it.

        `iterdir` on a path that is not there raises, and nothing between here and
        `run_tagger_loop` catches it -- so one unmounted volume ended the background
        round for the lifetime of the process, and /health reported the whole service
        degraded because of it.
        """
        self.settings.eps_folder_path = str(self.root / 'not-mounted')

        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_label_folders()

        parse_folder.assert_not_called()

    def test_the_single_file_path_agrees_with_the_folder_scan(self):
        """Two independent decisions, one rule. They drifted apart once already."""
        song = self.make_song(self.eps / '__TODO' / 'Some Release')

        with (
            patch.object(tagger_module.Tagger, 'parse_song') as parse_song,
            patch.object(tagger_module, 'settings', self.settings, create=True),
        ):
            tagger_module.TagSingleFile(song)

        self.assertEqual(SongTypeEnum.GENERIC, parse_song.call_args.args[1])


class MovedImportQueueTest(TaggerTestCase):
    """`import_folder_path` outside the EPs root: a config change, not a code change (bug 087)."""

    def setUp(self):
        super().setUp()
        self.queue = self.root / 'import'
        self.settings.import_folder_path = str(self.queue)

    def test_a_label_folder_named_like_the_old_queue_is_no_longer_special_by_name(self):
        # Only the configured location is the queue; an underscore folder still is no label.
        self.make_song(self.eps / 'Roughstate' / 'Some Release')
        self.make_song(self.eps / '__Free&None' / 'Some Release')

        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_label_folders()

        types = {call.args[0].name: call.args[1] for call in parse_folder.call_args_list}
        self.assertEqual({'Roughstate': SongTypeEnum.LABEL, '__Free&None': SongTypeEnum.GENERIC}, types)

    def test_the_moved_queue_is_still_walked_as_generic(self):
        self.make_song(self.queue / 'Some Release')

        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_import_queue()

        parse_folder.assert_called_once_with(self.queue, SongTypeEnum.GENERIC)

    def test_a_queue_inside_the_eps_root_is_left_to_the_label_walk(self):
        self.settings.import_folder_path = str(self.eps / '__TODO')
        (self.eps / '__TODO').mkdir()

        with patch.object(self.tagger, 'parse_folder') as parse_folder:
            self.tagger._parse_import_queue()

        parse_folder.assert_not_called()

    def test_the_moved_queue_is_a_root_for_new_library_files(self):
        self.tagger._queue_new_library_files()

        roots = self.processed.queue_new_library_files.call_args.args[0]
        self.assertIn(str(self.queue), roots)

    def test_a_file_in_the_moved_queue_is_generic(self):
        song = self.make_song(self.queue / 'Some Release')
        with patch.object(tagger_module, 'Settings', return_value=self.settings):
            self.assertEqual(SongTypeEnum.GENERIC, tagger_module.detect_song_type(song))

    def test_a_file_in_a_label_folder_is_still_a_label(self):
        song = self.make_song(self.eps / 'Roughstate' / 'Some Release')
        with patch.object(tagger_module, 'Settings', return_value=self.settings):
            self.assertEqual(SongTypeEnum.LABEL, tagger_module.detect_song_type(song))


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

    def test_a_run_holds_the_processed_snapshot_for_the_walk_only(self):
        # Loaded after the pending pass (so it already reflects that work) and dropped
        # after the walk, also when the walk raises.
        order = []
        self.processed.load_snapshot.side_effect = lambda: order.append('load')
        self.processed.drop_snapshot.side_effect = lambda: order.append('drop')
        with (
            patch.object(self.tagger, '_process_pending', side_effect=lambda: order.append('pending')),
            patch.object(self.tagger, '_parse_label_folders', side_effect=lambda: order.append('walk')),
            patch.object(self.tagger, '_parse_channel_folders'),
            patch.object(self.tagger, '_parse_generic_folders'),
        ):
            self.tagger.run()
        self.assertEqual(order, ['pending', 'load', 'walk', 'drop'])

    def test_the_snapshot_is_dropped_even_when_the_walk_raises(self):
        with (
            patch.object(self.tagger, '_parse_label_folders', side_effect=RuntimeError('share gone')),
            self.assertRaises(RuntimeError),
        ):
            self.tagger.run()
        self.processed.drop_snapshot.assert_called_once()

    def test_a_run_asks_lms_to_pick_up_what_changed(self):
        with (
            patch.object(self.tagger, '_parse_label_folders'),
            patch.object(self.tagger, '_parse_channel_folders'),
            patch.object(self.tagger, '_parse_generic_folders'),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger.run()
        trigger.trigger.assert_called_once()


class PendingPassTest(TaggerTestCase):
    """What a rule change queued is tagged from the table, before and independent of the walk."""

    def setUp(self):
        super().setUp()
        patcher = patch.object(tagger_module, 'Settings', return_value=self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def queue(self, *pages):
        self.processed.pending_paths.side_effect = [list(map(str, page)) for page in pages] + [[]]

    def test_the_queue_is_tagged_before_any_folder_is_walked(self):
        order = []
        song = self.make_song(self.music / 'Youtube' / 'channel')
        self.queue([song])
        with (
            patch.object(self.tagger, '_try_parse', side_effect=lambda *a: order.append('pending')),
            patch.object(self.tagger, '_parse_label_folders', side_effect=lambda: order.append('walk')),
            patch.object(self.tagger, '_parse_channel_folders'),
            patch.object(self.tagger, '_parse_generic_folders'),
        ):
            self.tagger.run()
        self.assertEqual(order, ['pending', 'walk'])

    def test_each_queued_file_gets_the_type_its_location_gives(self):
        label = self.make_song(self.eps / 'Scantraxx' / 'SCAN123')
        youtube = self.make_song(self.music / 'Youtube' / 'channel')
        self.queue([label, youtube])
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger._process_pending()
        self.assertEqual(
            [(call.args[0], call.args[1]) for call in try_parse.call_args_list],
            [(label, SongTypeEnum.LABEL), (youtube, SongTypeEnum.YOUTUBE)],
        )

    def test_pages_are_keyed_on_the_last_path_handed_out(self):
        first = self.make_song(self.music / 'Soundcloud' / 'a')
        second = self.make_song(self.music / 'Soundcloud' / 'b')
        self.queue([first], [second])
        with patch.object(self.tagger, '_try_parse'):
            self.tagger._process_pending()
        self.assertEqual(
            [call.args for call in self.processed.pending_paths.call_args_list],
            [
                (Tagger.PENDING_BATCH, '', 'genre_decision'),
                (Tagger.PENDING_BATCH, str(first), 'genre_decision'),
                (Tagger.PENDING_BATCH, str(second), 'genre_decision'),
            ],
        )

    def test_the_queue_is_served_reason_by_reason_in_the_helpers_order(self):
        # The helper decides the order (decisions before bulk); the pass pages each reason
        # from the start of the key range, so a decision's page is never behind bulk's.
        decision = self.make_song(self.music / 'Youtube' / 'z')
        bulk = self.make_song(self.music / 'Soundcloud' / 'a')
        self.processed.pending_reasons.return_value = ['genre_decision', None]
        self.processed.pending_paths.side_effect = [[str(decision)], [], [str(bulk)], []]
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger._process_pending()
        self.assertEqual([call.args[0] for call in try_parse.call_args_list], [decision, bulk])
        self.assertEqual(
            [call.args for call in self.processed.pending_paths.call_args_list],
            [
                (Tagger.PENDING_BATCH, '', 'genre_decision'),
                (Tagger.PENDING_BATCH, str(decision), 'genre_decision'),
                (Tagger.PENDING_BATCH, '', None),
                (Tagger.PENDING_BATCH, str(bulk), None),
            ],
        )

    def test_a_stop_request_ends_the_pass_between_reasons(self):
        self.processed.pending_reasons.return_value = ['genre_decision', 'rescan_all']
        self.tagger.stop_requested = True
        self.tagger._process_pending()
        self.processed.pending_paths.assert_not_called()

    def test_files_the_scanner_knows_and_the_tagger_never_saw_are_queued_first(self):
        # Every walk root plus the EPs root, and only the extensions the walk enables.
        self.processed.queue_new_library_files.return_value = 3
        with patch.object(self.tagger, '_walk'):
            self.tagger.run(walk=False)
        roots, extensions = self.processed.queue_new_library_files.call_args.args
        self.assertEqual(roots[0], str(self.eps))
        self.assertIn(str(self.music / 'Youtube'), roots)
        self.assertIn(str(self.music / 'Warm Up Mixes'), roots)
        self.assertEqual(extensions, ('mp3', 'flac', 'm4a'))

    def test_a_run_without_the_walk_serves_the_queue_and_touches_no_folder(self):
        order = []
        with (
            patch.object(self.tagger, '_process_pending', side_effect=lambda: order.append('pending')),
            patch.object(self.tagger, '_walk', side_effect=lambda *a: order.append('walk')),
        ):
            self.tagger.run(walk=False)
        self.assertEqual(order, ['pending'])
        self.processed.load_snapshot.assert_not_called()

    def test_a_queued_file_that_is_gone_is_forgotten_rather_than_retried_forever(self):
        gone = self.music / 'Youtube' / 'channel' / 'gone.mp3'
        self.queue([gone])
        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger._process_pending()
        try_parse.assert_not_called()
        self.processed.forget.assert_called_once_with(str(gone))

    def test_the_folders_written_are_handed_to_lms_once_each(self):
        a = self.make_song(self.music / 'Soundcloud' / 'artist', 'a.mp3')
        b = self.make_song(self.music / 'Soundcloud' / 'artist', 'b.mp3')
        self.queue([a, b])
        with (
            patch.object(self.tagger, '_try_parse', return_value=True),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger._process_pending()
        trigger.notify.assert_called_once_with([str(a.parent)])

    def test_a_folder_where_nothing_was_written_is_not_handed_to_lms(self):
        a = self.make_song(self.music / 'Soundcloud' / 'artist', 'a.mp3')
        b = self.make_song(self.music / 'Soundcloud' / 'other', 'b.mp3')
        self.queue([a, b])
        with (
            patch.object(self.tagger, '_try_parse', side_effect=lambda path, *_: path == b),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger._process_pending()
        trigger.notify.assert_called_once_with([str(b.parent)])

    def test_the_parallel_path_hands_lms_only_the_folder_of_a_saved_file(self):
        self.tagger.parallel = True
        a = self.make_song(self.music / 'Soundcloud' / 'artist', 'a.mp3')
        b = self.make_song(self.music / 'Soundcloud' / 'other', 'b.mp3')
        self.queue([a, b])
        with (
            patch.object(
                Tagger, '_parse_worker', side_effect=lambda file, *_: (file, 'SAVED' if file == str(b) else 'OK')
            ),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger._process_pending()
        trigger.notify.assert_called_once_with([str(b.parent)])

    def test_a_stop_request_ends_the_pass_between_files(self):
        a = self.make_song(self.music / 'Soundcloud' / 'artist', 'a.mp3')
        b = self.make_song(self.music / 'Soundcloud' / 'artist', 'b.mp3')
        self.queue([a, b], [self.make_song(self.music / 'Soundcloud' / 'other')])

        def stop(*_):
            self.tagger.stop_requested = True

        with patch.object(self.tagger, '_try_parse', side_effect=stop) as try_parse:
            self.tagger._process_pending()
        self.assertEqual(try_parse.call_count, 1)
        self.assertEqual(self.processed.pending_paths.call_count, 1)

    def test_the_parallel_path_hands_every_queued_file_to_a_worker(self):
        self.tagger.parallel = True
        a = self.make_song(self.music / 'Youtube' / 'channel', 'a.mp3')
        b = self.make_song(self.eps / 'Scantraxx' / 'SCAN1', 'b.mp3')
        self.queue([a, b])
        with patch.object(Tagger, '_parse_worker', return_value=('x', 'OK')) as worker:
            self.tagger._process_pending()
        self.assertEqual(
            sorted(call.args[:2] for call in worker.call_args_list),
            sorted([(str(a), 'YOUTUBE'), (str(b), 'LABEL')]),
        )

    def test_the_parallel_path_pauses_after_a_slice_that_did_work(self):
        """The tagger shares the GIL with the API. After 0.67.0 a 32.000-file queue ran
        on sixteen threads without a break and /health timed out for over an hour. Every
        slice that parsed something ends with a pause so the event loop gets a turn."""
        self.tagger.parallel = True
        songs = [self.make_song(self.music / 'Youtube' / 'channel', f'{i}.mp3') for i in range(5)]
        self.queue(songs)
        with (
            patch.object(Tagger, 'PARALLEL_SLICE', 2),
            patch.object(tagger_module, 'TAGGER_BATCH_PAUSE', 0.25),
            patch.object(Tagger, '_parse_worker', return_value=('x', 'OK')),
            patch.object(tagger_module.time, 'sleep') as sleep,
        ):
            self.tagger._process_pending()
        # Five files in slices of two: three slices, three pauses.
        self.assertEqual(sleep.call_args_list, [call(0.25)] * 3)

    def test_a_slice_of_up_to_date_files_costs_no_pause(self):
        self.tagger.parallel = True
        self.queue([self.make_song(self.music / 'Youtube' / 'channel', 'a.mp3')])
        with (
            patch.object(Tagger, '_parse_worker', return_value=('x', 'SKIPPED')),
            patch.object(tagger_module.time, 'sleep') as sleep,
        ):
            self.tagger._process_pending()
        sleep.assert_not_called()

    def test_a_stop_request_ends_the_parallel_pass_between_slices(self):
        self.tagger.parallel = True
        songs = [self.make_song(self.music / 'Youtube' / 'channel', f'{i}.mp3') for i in range(4)]
        self.queue(songs)

        def stop(*_):
            self.tagger.stop_requested = True
            return ('x', 'OK')

        with (
            patch.object(Tagger, 'PARALLEL_SLICE', 2),
            patch.object(Tagger, '_parse_worker', side_effect=stop) as worker,
            patch.object(tagger_module.time, 'sleep') as sleep,
        ):
            self.tagger._process_pending()
        # The first slice may run to completion; the second is never handed out.
        self.assertLessEqual(worker.call_count, 2)
        sleep.assert_not_called()

    def test_an_empty_queue_walks_nothing_and_asks_once(self):
        self.tagger._process_pending()
        self.processed.pending_paths.assert_called_once_with(Tagger.PENDING_BATCH, '', 'genre_decision')

    def test_no_queued_reason_means_no_page_is_asked_for(self):
        self.processed.pending_reasons.return_value = []
        self.tagger._process_pending()
        self.processed.pending_paths.assert_not_called()


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

    def test_a_directory_named_like_a_song_is_not_parsed_as_one(self):
        """`glob` matches names, and the library really does contain folders ending in `.mp3`.

        `/mnt/music/EPs/This is Terror/TITCD018 - Srb - Rocket Science (2015).mp3` is a
        directory. It reached mutagen on every pass and came back as
        `IsADirectoryError: [Errno 21]`, which the parallel worker logs as `Parse_song
        failed` -- five a night on production on 2026-09-10, and never fewer, because
        nothing about a directory becomes readable on the next run.
        """
        folder = self.music / 'Soundcloud' / 'artist'
        song = self.make_song(folder)
        (folder / 'Srb - Rocket Science (2015).mp3').mkdir()

        with patch.object(self.tagger, '_try_parse') as try_parse:
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)

        self.assertEqual([call.args[0] for call in try_parse.call_args_list], [song])

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

    def test_hidden_subfolders_are_not_walked(self):
        # A redownload stages its file in a dot folder beside the one it replaces.
        folder = self.music / 'Soundcloud' / 'artist'
        self.make_song(folder / '.muma-redownload-x1')
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

    def test_the_walk_pauses_only_after_a_slice_that_parsed_something(self):
        """A full walk visits 300.000 files of which nearly all are up to date. A pause
        per slice of those would add hours to a round that changes nothing; only a slice
        in which a worker actually ran the rules costs the API-turn."""
        folder = self.music / 'Soundcloud' / 'artist'
        for name in ('a.mp3', 'b.mp3', 'c.mp3'):
            self.make_song(folder, name)
        self.tagger.parallel = True
        statuses = iter(['SKIPPED', 'SKIPPED', 'OK'])
        with (
            patch.object(Tagger, 'PARALLEL_SLICE', 2),
            patch.object(Tagger, '_parse_worker', side_effect=lambda *_: ('x', next(statuses))),
            patch.object(tagger_module.time, 'sleep') as sleep,
        ):
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        sleep.assert_called_once_with(tagger_module.TAGGER_BATCH_PAUSE)

    def test_lms_hears_about_a_folder_only_when_a_file_in_it_was_written(self):
        """A full run visits every folder and leaves nearly all of them as they were.

        Every one of those used to be a scan request anyway: 13.798 in three hours on
        2026-09-18 against 7 files saved, and LMS re-read ~1.000 files from the NAS per
        request, back to back, for hours. A folder nothing touched is not news.
        """
        folder = self.music / 'Soundcloud' / 'artist'
        self.make_song(folder)
        with (
            patch.object(self.tagger, '_try_parse', return_value=False),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        trigger.notify.assert_not_called()

        with (
            patch.object(self.tagger, '_try_parse', return_value=True),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        trigger.notify.assert_called_once_with([str(folder)])

    def test_the_parallel_path_tells_lms_only_about_a_saved_file(self):
        folder = self.music / 'Soundcloud' / 'artist'
        for name in ('a.mp3', 'b.mp3'):
            self.make_song(folder, name)
        self.tagger.parallel = True
        with (
            patch.object(Tagger, '_parse_worker', return_value=('x', 'OK')),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        trigger.notify.assert_not_called()

        with (
            patch.object(Tagger, '_parse_worker', side_effect=[('a', 'OK'), ('b', 'SAVED')]),
            patch.object(tagger_module, 'lms_scan_trigger') as trigger,
        ):
            self.tagger.parse_folder(folder, SongTypeEnum.SOUNDCLOUD)
        trigger.notify.assert_called_once_with([str(folder)])


class TryParseTest(TaggerTestCase):
    def test_reports_whether_the_file_was_written(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song', return_value=MagicMock(saved=True)):
            self.assertTrue(self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD))
        with patch.object(Tagger, 'parse_song', return_value=MagicMock(saved=False)):
            self.assertFalse(self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD))
        self.processed.needs_processing.return_value = False
        self.assertFalse(self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD))

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

    def test_the_mtime_stored_is_the_one_after_the_save(self):
        # A written file has a newer mtime than the stat before parse_song; storing the old
        # one made every file the tagger wrote read as "changed" on the next walk.
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        os.utime(song, (1000.0, 1000.0))

        def write_the_file(*_):
            os.utime(song, (2000.0, 2000.0))
            return MagicMock(saved=True)

        with patch.object(Tagger, 'parse_song', side_effect=write_the_file):
            self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)
        self.assertEqual(self.processed.mark_processed.call_args.args[1], 2000.0)
        self.processed.reset_mock()
        os.utime(song, (1000.0, 1000.0))
        with patch.object(Tagger, 'parse_song', side_effect=write_the_file):
            Tagger._parse_worker(str(song), 'SOUNDCLOUD')
        self.assertEqual(self.processed.mark_processed.call_args.args[1], 2000.0)

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

    def test_a_retag_is_handed_what_the_download_knew(self):
        # The whole point: a walk of the tree carries no info dict, so without this the
        # second pass over a SoundCloud file is blind to everything the first one saw.
        tagger_module.download_info.stored_info.return_value = {'genre': 'Uptempo Hardcore'}
        with patch.object(tagger_module, 'SoundcloudSong') as song_class:
            Tagger.parse_song(Path('/music/a.mp3'), SongTypeEnum.SOUNDCLOUD)
        assert song_class.call_args.args[1] == {'genre': 'Uptempo Hardcore'}

    def test_the_downloaders_own_info_is_not_replaced_by_the_stored_copy(self):
        tagger_module.download_info.stored_info.return_value = {'genre': 'stale'}
        with patch.object(tagger_module, 'SoundcloudSong') as song_class:
            Tagger.parse_song(Path('/music/a.mp3'), SongTypeEnum.SOUNDCLOUD, extra_info={'genre': 'fresh'})
        assert song_class.call_args.args[1] == {'genre': 'fresh'}
        tagger_module.download_info.stored_info.assert_not_called()


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

    def test_a_written_file_is_reported_as_saved(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        with patch.object(Tagger, 'parse_song', return_value=MagicMock(saved=True)):
            self.assertEqual(Tagger._parse_worker(str(song), 'SOUNDCLOUD')[1], 'SAVED')
        with patch.object(Tagger, 'parse_song', return_value=MagicMock(saved=False)):
            self.assertEqual(Tagger._parse_worker(str(song), 'SOUNDCLOUD')[1], 'OK')

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


class FailedAttemptTest(TaggerTestCase):
    """A file that always fails is backed off and parked, not retried every round forever.

    Each failed round used to log an ERROR, and every ERROR is an event and an alert
    push: a single broken file buzzed the phone every five minutes. Bug report 051.
    """

    def run_failing(self, attempts, worker=True):
        """Run one failing attempt with the helper reporting `attempts`; return the log records."""
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        self.processed.mark_failed.return_value = attempts
        with (
            patch.object(Tagger, 'parse_song', side_effect=RuntimeError('boom')),
            self.assertLogs(level='INFO') as logs,
        ):
            if worker:
                Tagger._parse_worker(str(song), 'SOUNDCLOUD')
            else:
                self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)
        return song, logs.records

    def levels(self, records):
        return [record.levelname for record in records if 'boom' in record.getMessage()]

    def test_every_failure_is_counted_with_the_files_mtime_and_the_threshold(self):
        song, _ = self.run_failing(1)
        path, mtime, park_after = self.processed.mark_failed.call_args.args
        self.assertEqual(path, str(song))
        self.assertEqual(mtime, song.stat().st_mtime)
        self.assertEqual(park_after, tagger_module.TAGGER_PARK_AFTER)

    def test_the_first_failure_is_a_warning_not_an_error(self):
        _, records = self.run_failing(1)
        self.assertEqual(self.levels(records), ['WARNING'])
        self.assertIsNotNone(records[-1].exc_info)

    def test_a_retry_that_fails_again_is_no_new_error(self):
        _, records = self.run_failing(2)
        self.assertEqual(self.levels(records), ['INFO'])

    def test_the_failure_that_parks_the_file_is_one_warning(self):
        _, records = self.run_failing(tagger_module.TAGGER_PARK_AFTER)
        self.assertEqual(self.levels(records), ['WARNING'])
        self.assertIn('Parked', records[-1].getMessage())

    def test_the_serial_path_counts_failures_too(self):
        _, records = self.run_failing(2, worker=False)
        self.processed.mark_failed.assert_called_once()
        self.assertEqual(self.levels(records), ['INFO'])

    def test_an_uncounted_failure_is_still_an_error(self):
        # The database could not be written: nothing is known about earlier attempts.
        _, records = self.run_failing(0)
        self.assertEqual(self.levels(records), ['ERROR'])

    def test_a_broken_file_is_counted_as_well_as_recorded(self):
        song = self.make_song(self.music / 'Soundcloud' / 'artist')
        self.processed.mark_failed.return_value = 1
        with (
            patch.object(Tagger, 'parse_song', side_effect=PermissionError('denied')),
            self.assertLogs(level='WARNING'),
        ):
            self.tagger._try_parse(song, SongTypeEnum.SOUNDCLOUD)
        self.processed.mark_failed.assert_called_once()
        tagger_module.broken_song_helper.add.assert_called_once_with(str(song), 'PermissionError')


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


class EnvNumberTest(unittest.TestCase):
    """`TAGGER_WORKERS` and `TAGGER_BATCH_PAUSE` are read once at import, through this."""

    def test_unset_and_blank_fall_back_to_the_default(self):
        with patch.dict(os.environ, {'TAGGER_WORKERS': ''}, clear=False):
            self.assertEqual(tagger_module._env_number('TAGGER_WORKERS', 12, int), 12)
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(tagger_module._env_number('TAGGER_WORKERS', 12, int), 12)

    def test_a_value_is_cast(self):
        with patch.dict(os.environ, {'TAGGER_WORKERS': '4', 'TAGGER_BATCH_PAUSE': '0.1'}):
            self.assertEqual(tagger_module._env_number('TAGGER_WORKERS', 12, int), 4)
            self.assertEqual(tagger_module._env_number('TAGGER_BATCH_PAUSE', 0.5), 0.1)

    def test_garbage_is_logged_and_ignored(self):
        with patch.dict(os.environ, {'TAGGER_WORKERS': 'lots'}), self.assertLogs(level='WARNING'):
            self.assertEqual(tagger_module._env_number('TAGGER_WORKERS', 12, int), 12)
