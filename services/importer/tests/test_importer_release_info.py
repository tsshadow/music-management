"""Placing a release by what its .nfo and Deezer say (docs/designs/release-info-enrichment/).

The fixture is the release seen on production on 2026-10-02 that never reached `EPs/B2S`.
"""

import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.mock_base('Cache')

from services.common import release_nfo  # noqa: E402
from services.common.store_lookup import Budget, StoreCache, _Pace  # noqa: E402
from services.importer import mover as mover_module  # noqa: E402
from services.importer import settle  # noqa: E402
from services.importer.label_match import LabelIndex  # noqa: E402
from services.importer.label_proposal_store import KnownProposal  # noqa: E402
from services.importer.release_info import ReleaseInfo  # noqa: E402
from services.importer.renamer import Renamer  # noqa: E402
from services.importer.tests.test_importer_mover_cycle import MoverOnDiskTest  # noqa: E402

MINUS_MILITIA = (
    'Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-SINGLE-WEB-2026-UTNG'
)
NFO = """
       Rip.date: 01.10.2026                Year....: 2026
       Company.: B2S                       Length..: 03:24
       Rls.type: WEB                       Tracks..: 01

       Url:https://deezer.com/album/1104265012
"""
DEEZER = {'id': 1104265012, 'label': 'b2s Records', 'upc': '8719244873593', 'release_date': '2026-10-02'}


class MemoryDb:
    """`release_store_lookups` as a dict."""

    def __init__(self):
        self.rows = {}

    @contextmanager
    def connection(self):
        db = self

        class Cursor:
            row = None

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, params):
                if sql.startswith('SELECT'):
                    self.row = db.rows.get(params)
                else:
                    db.rows[(params[0], params[1])] = params[2:]

            def fetchone(self):
                return self.row

        class Connection:
            def cursor(self):
                return Cursor()

            def commit(self):
                pass

        yield Connection()


def write_release(base, folder, nfo=NFO):
    path = os.path.join(base, folder)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, '01-minus_militia_and_nolz_-_recover_the_archive.mp3'), 'w') as handle:
        handle.write('audio')
    if nfo is not None:
        with open(os.path.join(path, '00-release.nfo'), 'wb') as handle:
            handle.write(nfo.encode('cp437'))
    return path


class StoreDouble:
    """A StoreCache over a dict and a recorded Deezer answer; counts the requests."""

    def __init__(self, answer=(200, DEEZER)):
        self.requests = []
        self.db = MemoryDb()

        def http_get(url):
            self.requests.append(url)
            if isinstance(answer, Exception):
                raise answer
            return answer

        self.cache = StoreCache(
            self.db.connection, http_get=http_get, pace=_Pace(0, clock=lambda: 0.0, sleep=lambda _s: None)
        )


class ReleaseInfoTest(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(tempfile.TemporaryDirectory())
        self.index = LabelIndex(['B2S', 'Scantraxx', 'Brutal Kuts'])

    def test_the_nfo_company_places_minus_militia_under_b2s(self):
        path = write_release(self.root, MINUS_MILITIA)
        store = StoreDouble()

        placement = ReleaseInfo(store.cache).placement(path, self.index, Budget(5))

        self.assertEqual(('B2S', 'nfo:company', 'B2S'), (placement.label, placement.source, placement.stated))

    def test_offline_the_nfo_alone_still_places_it(self):
        path = write_release(self.root, MINUS_MILITIA)

        placement = ReleaseInfo(StoreDouble(OSError('offline')).cache).placement(path, self.index, Budget(5))

        self.assertEqual('B2S', placement.label)

    def test_deezer_is_the_fallback_when_the_nfo_names_no_known_label(self):
        path = write_release(self.root, MINUS_MILITIA, NFO.replace('Company.: B2S', 'Company.: B2S Recordz Ltd X'))

        placement = ReleaseInfo(StoreDouble().cache).placement(path, self.index, Budget(5))

        self.assertEqual(('B2S', 'deezer', 'b2s Records'), (placement.label, placement.source, placement.stated))

    def test_two_sources_naming_two_folders_place_nothing(self):
        path = write_release(self.root, MINUS_MILITIA, NFO.replace('Company.: B2S', 'Company.: Brutal Kuts'))

        self.assertIsNone(ReleaseInfo(StoreDouble().cache).placement(path, self.index, Budget(5)))

    def test_a_label_without_a_folder_places_nothing(self):
        path = write_release(self.root, MINUS_MILITIA, 'Label....: Henergy Records\n')

        self.assertIsNone(ReleaseInfo(StoreDouble().cache).placement(path, self.index, None))

    def test_the_nfo_is_read_once_until_it_changes(self):
        path = write_release(self.root, MINUS_MILITIA)
        info = ReleaseInfo(StoreDouble().cache)
        with patch.object(release_nfo, 'read', wraps=release_nfo.read) as read:
            info.nfo(path)
            info.nfo(path)
            self.assertEqual(1, read.call_count)
            nfo = os.path.join(path, '00-release.nfo')
            with open(nfo, 'ab') as handle:
                handle.write(b'Catalog Nr..: BTS001\n')
            os.utime(nfo, (1, 1))
            self.assertEqual('BTS001', info.catalogue_number(path))
            self.assertEqual(2, read.call_count)


class RenamerTakesTheNfoCatalogueNumberTest(unittest.TestCase):
    def test_a_name_without_one_gets_the_nfos(self):
        root = self.enterContext(tempfile.TemporaryDirectory())
        folder = 'Rawcore_-_Love_Of_Yesterday-WEB-2026'
        write_release(root, folder, 'Label.......: Rawcore\nCatalog Nr..: RAW046\n')
        renamer = Renamer()
        renamer.settings = type('S', (), {'import_folder_path': root, 'delimiter': '/'})()
        with (
            patch.object(settle, 'settle_seconds', return_value=0),
            patch('services.importer.renamer.lms_scan_trigger'),
        ):
            renamer.run()
        self.assertEqual(['RAW046 - ' + folder], os.listdir(root))


class MoverPlacesByReleaseInfoTest(MoverOnDiskTest):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.eps, 'B2S'))
        self.deezer = StoreDouble()
        self.mover.release_info = ReleaseInfo(self.deezer.cache)
        self.post = self.enterContext(patch.object(mover_module, 'post_processing_songs', return_value=1))

    def test_minus_militia_lands_under_b2s_with_one_push(self):
        write_release(self.imports, MINUS_MILITIA)

        self.mover.run()

        self.assertTrue(os.path.isdir(os.path.join(self.eps, 'B2S', MINUS_MILITIA)))
        self.assertEqual([], os.listdir(self.imports))
        self.assertEqual(date.today(), self.post.call_args.kwargs['arrival_date'])
        message = self.notify.call_args.args[0]
        self.assertIn('Label: B2S', message)
        self.assertIn('Label from: nfo:company (B2S)', message)
        self.assertIs(self.notify.call_args.kwargs['push'], True)
        # The Deezer answer is in the cache before the tagging pass reads it.
        self.assertIn(('deezer', '1104265012'), self.deezer.db.rows)
        self.store.record.assert_not_called()

    def test_a_backlog_release_is_placed_without_a_push_and_with_its_arrival_date(self):
        write_release(self.imports, MINUS_MILITIA)
        self.store.rows[MINUS_MILITIA] = KnownProposal('new', None, 'fp', datetime(2026, 9, 25, 8, 0))

        self.mover.run()

        self.assertIs(self.notify.call_args.kwargs['push'], False)
        self.assertEqual(date(2026, 9, 25), self.post.call_args.kwargs['arrival_date'])

    def test_switched_off_it_is_a_proposal_as_before(self):
        self.mover.settings.import_place_by_label_name = False
        write_release(self.imports, MINUS_MILITIA)

        self.mover.run()

        self.assertTrue(os.path.isdir(os.path.join(self.imports, MINUS_MILITIA)))
        self.store.record.assert_called_once()

    def test_the_per_cycle_cap_defers_the_rest_to_the_next_cycle(self):
        self.mover.settings.import_label_name_moves_per_cycle = 1
        write_release(self.imports, MINUS_MILITIA)
        write_release(self.imports, MINUS_MILITIA.replace('Recover', 'Discover'))

        self.mover.run()
        self.assertEqual(1, len(os.listdir(os.path.join(self.eps, 'B2S'))))
        self.mover.run()
        self.assertEqual(2, len(os.listdir(os.path.join(self.eps, 'B2S'))))

    def test_store_lookups_switched_off_send_no_request(self):
        self.mover.settings.import_store_lookups = False
        write_release(self.imports, MINUS_MILITIA)

        self.mover.run()

        self.assertEqual([], self.deezer.requests)
        self.assertTrue(os.path.isdir(os.path.join(self.eps, 'B2S', MINUS_MILITIA)))

    def test_a_catalogue_rule_still_wins_over_the_nfo(self):
        self.mover.get_label.return_value = 'Scantraxx'
        folder = 'SCAN123 - ' + MINUS_MILITIA
        write_release(self.imports, folder)

        self.mover.run()

        self.assertTrue(os.path.isdir(os.path.join(self.eps, 'Scantraxx', folder)))


if __name__ == '__main__':
    unittest.main()
