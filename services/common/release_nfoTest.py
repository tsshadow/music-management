"""Reading scene .nfo files, against layouts found in the production import queue."""

import os
import tempfile
import unittest

from services.common import release_nfo

# The Minus Militia release of 2026-10-02 (UTNG), two pairs to a line, as decoded from CP437.
UTNG = """
                    Up To No Good Presents

              Minus Militia & Nolz - Recover The Archive (Official Hardbass 2026 Anthem

       Rip.date: 01.10.2026                Year....: 2026
       Company.: B2S                       Length..: 03:24
       Rls.type: WEB                       Tracks..: 01
       Genre...: Techno                    Size....: 7.78 MB
       Encoder.: LAME                      Quality.: 320kbps 44.kHz

       Url:https://deezer.com/album/1104265012
"""

# A one-column layout with a catalogue number and a localised Deezer URL.
ONE_COLUMN = """
   Artist......: Rawcore
   Label.......: Rawcore
   Catalog Nr..: RAW046
   Genre.......: Hardcore
   Url.........: https://www.deezer.com/en/album/93254283
   Url.........: https://www.beatport.com/release/love-of-yesterday/4567890
"""


class ParseTest(unittest.TestCase):
    def test_the_two_column_utng_layout(self):
        info = release_nfo.parse(UTNG)

        self.assertEqual('B2S', info.label)
        self.assertEqual('company', info.label_key)
        self.assertIsNone(info.catalogue_number)
        self.assertEqual('1104265012', info.link('deezer').album_id)

    def test_label_beats_company_and_the_catalogue_number_is_read(self):
        info = release_nfo.parse(ONE_COLUMN + '   Company.....: Something Else\n')

        self.assertEqual(('Rawcore', 'label'), (info.label, info.label_key))
        self.assertEqual('RAW046', info.catalogue_number)

    def test_every_store_link_is_found_once(self):
        info = release_nfo.parse(ONE_COLUMN + ONE_COLUMN)

        self.assertEqual(
            [('deezer', '93254283'), ('beatport', '4567890')], [(link.store, link.album_id) for link in info.links]
        )

    def test_placeholder_values_are_no_label(self):
        self.assertIsNone(release_nfo.parse('Label....: N/A\n').label)

    def test_a_trailing_carriage_return_is_not_part_of_the_value(self):
        self.assertEqual('Break The Rules Records', release_nfo.parse('Label....: Break The Rules Records\r\n').label)

    def test_a_upc_is_not_a_catalogue_number(self):
        self.assertIsNone(release_nfo.parse('Catalog...: 10368151\n').catalogue_number)
        self.assertIsNone(release_nfo.nfo_catalogue_number('8719244873593'))
        self.assertEqual('OPC006PRO', release_nfo.nfo_catalogue_number('OPC006PRO'))

    def test_block_art_after_a_value_is_dropped(self):
        self.assertEqual('Rawcore', release_nfo.parse('Label....: Rawcore █▓▒\n').label)


class ReadTest(unittest.TestCase):
    def test_reads_the_cp437_file_in_a_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, '00-release.nfo'), 'wb') as handle:
                handle.write(b'\xdb\xdb\x00 ' + UTNG.encode('cp437'))

            info = release_nfo.read(folder)

        self.assertEqual('B2S', info.label)

    def test_no_nfo_is_none(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(release_nfo.read(folder))
        self.assertIsNone(release_nfo.read('/does/not/exist'))


if __name__ == '__main__':
    unittest.main()
