"""The `__TODO` label repair: what it finds, what it derives, and that it only ever queues (bug 087)."""

import os
import unittest
from unittest.mock import MagicMock

from services.importer.label_resolver import LabelProposal
from services.tagger.todo_label_repair import REASON, TodoLabelRepair

EPS = '/mnt/music/EPs'
QUEUE = EPS + '/__TODO'


class TodoLabelRepairTest(unittest.TestCase):
    def setUp(self):
        self.tags: dict[str, tuple[str, str]] = {}
        self.paths: list[str] = []
        self.processed = MagicMock()
        self.processed.paths_under.side_effect = lambda roots, after, limit: [p for p in self.paths if p > after][
            :limit
        ]
        self.processed.mark_paths_for_rescan.side_effect = lambda paths, reason: len(paths)
        self.resolver = MagicMock(return_value=LabelProposal('Brutal Kuts', 'tag:label', 90, None))

    def repair(self, queue=QUEUE):
        settings = MagicMock(eps_folder_path=EPS, import_folder_path=queue)
        return TodoLabelRepair(
            settings=settings,
            processed_files=self.processed,
            reader=lambda path: self.tags.get(path, ('', '')),
            resolver=self.resolver,
        )

    def add(self, path, publisher='', copyright_=''):
        self.paths.append(path)
        self.paths.sort()
        self.tags[path] = (publisher, copyright_)

    def test_a_label_folder_file_derives_its_label_from_the_folder(self):
        self.add(EPS + '/Scantraxx/SCAN1 - X/a.mp3', '__TODO', '__TODO (2020)')

        page = self.repair().run_page()

        self.assertEqual(1, page['poisoned'])
        self.assertEqual({'Scantraxx': 1}, page['by_label'])
        self.assertEqual({'publisher': 1, 'copyright': 1}, page['by_field'])
        self.resolver.assert_not_called()

    def test_a_moved_release_with_only_a_poisoned_copyright_is_found(self):
        # LabelSong rewrote the publisher and kept the copyright: the half nobody fixed.
        self.add(EPS + '/Scantraxx/SCAN1 - X/a.mp3', 'Scantraxx', '__TODO (2020)')

        self.assertEqual({'copyright': 1}, self.repair().run_page()['by_field'])

    def test_a_queue_file_asks_the_importers_resolver_once_per_release(self):
        self.add(QUEUE + '/Release/a.mp3', '__TODO')
        self.add(QUEUE + '/Release/b.mp3', '__TODO')

        page = self.repair().run_page()

        self.assertEqual({'Brutal Kuts': 2}, page['by_label'])
        self.resolver.assert_called_once_with(QUEUE + '/Release', import_folder_name='__TODO')

    def test_a_queue_file_the_resolver_cannot_place_is_undecidable(self):
        self.resolver.return_value = LabelProposal(None, 'none', 0, None)
        self.add(QUEUE + '/Release/a.mp3', '__TODO')

        page = self.repair().run_page()

        self.assertEqual(1, page['undecidable_count'])
        self.assertEqual([QUEUE + '/Release/a.mp3'], page['undecidable'])
        self.assertEqual({}, page['by_label'])

    def test_an_underscore_folder_has_no_label_and_is_decidable(self):
        self.add(EPS + '/__Free&None/Release/a.mp3', '__TODO')

        page = self.repair().run_page()

        self.assertEqual({'no_label': 1}, page['by_area'])
        self.assertEqual(0, page['undecidable_count'])

    def test_clean_files_are_not_findings(self):
        self.add(EPS + '/Scantraxx/SCAN1 - X/a.mp3', 'Scantraxx', 'Scantraxx (2020)')
        self.add(EPS + '/Scantraxx/SCAN1 - X/b.mp3')

        page = self.repair().run_page()

        self.assertEqual((2, 0), (page['scanned'], page['poisoned']))

    def test_dry_run_queues_nothing(self):
        self.add(EPS + '/Scantraxx/SCAN1 - X/a.mp3', '__TODO')

        page = self.repair().run_page(apply=False)

        self.processed.mark_paths_for_rescan.assert_not_called()
        self.assertEqual(0, page['queued'])

    def test_apply_queues_every_poisoned_file_under_its_own_reason(self):
        self.add(EPS + '/Scantraxx/SCAN1 - X/a.mp3', '__TODO')
        self.add(EPS + '/Scantraxx/SCAN1 - X/b.mp3', 'Scantraxx')
        self.add(QUEUE + '/Release/a.mp3', '__TODO')

        page = self.repair().run_page(apply=True)

        self.processed.mark_paths_for_rescan.assert_called_once_with(
            [EPS + '/Scantraxx/SCAN1 - X/a.mp3', QUEUE + '/Release/a.mp3'], REASON
        )
        self.assertEqual(2, page['queued'])
        self.assertEqual([EPS + '/Scantraxx/SCAN1 - X/a.mp3', QUEUE + '/Release/a.mp3'], page['poisoned_paths'])

    def test_pages_carry_a_cursor_until_the_end(self):
        for index in range(5):
            self.add(f'{EPS}/L/R/{index}.mp3')

        first = self.repair().run_page(limit=3)
        second = self.repair().run_page(after=first['next_after'], limit=3)

        self.assertEqual((3, False), (first['scanned'], first['done']))
        self.assertEqual((2, True), (second['scanned'], second['done']))

    def test_a_queue_outside_the_label_tree_is_walked_too(self):
        roots = self.repair(queue='/mnt/music/import').roots()
        self.assertEqual([EPS, '/mnt/music/import'], roots)
        self.assertEqual([EPS], self.repair().roots())

    def test_a_moved_queue_still_recognises_the_legacy_value(self):
        queue = '/mnt/music/import'
        self.add(queue + '/Release/a.mp3', '__TODO')

        page = self.repair(queue=queue).run_page()

        self.assertEqual({'queue': 1}, page['by_area'])
        self.resolver.assert_called_once_with(os.path.join(queue, 'Release'), import_folder_name='import')


if __name__ == '__main__':
    unittest.main()
