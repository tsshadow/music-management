"""What counts as a catalogue number, against names seen on production (bug report 145)."""

import unittest

from services.common.catalogue_number import from_folder_name, is_catalogue_number, old_rule_prefix, rejection

# Prefixes of label folders on production on 2026-10-02, one per shape the old Renamer
# produced. Every one of them routes a release today, so the new rule must keep them all.
REAL_CATALOGUE_NUMBERS = (
    'SCAN123',
    'AREC118E',
    'DWX0716',
    'R909-81',
    '247HC465',
    'T3RDM0378',
    'CR.109',
    'ISRD_233',
    'BF_-_189',
    'GH-GOLD041',
    'KN_011-5',
    'HSF111-DJ',
    'GGM_RAW_001',
    'ENZYME_X_34',
    'DSB_REC_028',
    'JB-BPINT22-05',
    'HERESY-X-003',
    'RR_ALBUM_001B',
    'NOxEVO004',
    'TOFF087d',
    'Fusion250',
    'PRSPCTXTRMDIGI017',
    'CATALOGNUMBER061',
    'AVR2026048BP',
    'CLDG2026002',
    'BD26001440',
    'RMZ-82',
    '037',
    '5054197630866',
    '71-379',
)

# Prefixes the old Renamer gave folders in __TODO on 2026-10-02 that never reached a label.
NOT_CATALOGUE_NUMBERS = (
    'Official_Hardbass_2026_Anthem',
    'Official_Harmony_Of_Hardcore_2026_Anthem',
    'TIMELESS_FESTIVAL_2026_ANTHEM',
    'OFFICIAL_FACELESS_FESTIVAL_2024_OST',
    'Defqon.1_2024_Anthem',
    '2026_Remaster',
    '2026_Rework',
    'Equal2_Remix',
    'S3RL_Remix',
    'MI37_Extended_Rave_Mix',
    'Volume_1',
    'Part_2',
    'Pt._2',
    'Refix_V2',
    'Cenobite_Digital_52',
    'Rebirth_2024_Tool',
    'I_Made_This_Song_In_1_Hour_While_I_Was_Pooping',
    'Pokke_Herrie_Anthem26',
    '2026',
    '1',
    '',
    'DDRS014_Shi_Si_',
    'SCAN 123',
)


class IsCatalogueNumberTest(unittest.TestCase):
    def test_every_real_shape_is_accepted(self):
        for value in REAL_CATALOGUE_NUMBERS:
            with self.subTest(value=value):
                self.assertIsNone(rejection(value))

    def test_words_years_and_prose_are_refused(self):
        for value in NOT_CATALOGUE_NUMBERS:
            with self.subTest(value=value):
                self.assertFalse(is_catalogue_number(value))

    def test_the_reason_names_the_offending_part(self):
        self.assertEqual(rejection('Official_Hardbass_2026_Anthem'), 'word:Official')
        self.assertEqual(rejection('Anthem26'), 'word:Anthem26')
        self.assertEqual(rejection('Cenobite_Digital_52'), 'cased-words')
        self.assertEqual(rejection('2026'), 'year')
        self.assertEqual(rejection('B2S'), None)
        self.assertEqual(rejection('Scantraxx'), 'no-digit')
        self.assertEqual(rejection('A' * 25 + '1'), 'length')
        self.assertEqual(rejection('AB_CD_EF_GH_1'), 'parts')
        self.assertEqual(rejection('MRVSP@1'), 'chars')

    def test_surrounding_whitespace_is_ignored(self):
        self.assertTrue(is_catalogue_number(' SCAN123 '))


class FromFolderNameTest(unittest.TestCase):
    def test_the_minus_militia_release_has_no_catalogue_number(self):
        name = 'Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-SINGLE-WEB-2026-UTNG'
        self.assertIsNone(from_folder_name(name))
        # ...where the old rule took the anthem.
        self.assertEqual(old_rule_prefix(name), 'Official_Hardbass_2026_Anthem')

    def test_the_last_real_catalogue_number_wins(self):
        self.assertEqual(from_folder_name('Hexus_-_The_Mission-(HA037)-WEB-2026'), 'HA037')
        self.assertEqual(
            from_folder_name('Hyperactive-D_-_The_Lighthouse_(Extended_Mix)-(HOMAD022D)-WEB-FLAC-2026'), 'HOMAD022D'
        )

    def test_an_earlier_real_group_is_found_behind_a_word_group(self):
        self.assertEqual(from_folder_name('X_-_Y-(ABC123)-(2023_Edit)-WEB-2026'), 'ABC123')

    def test_old_rule_prefix_without_any_digit_group_is_none(self):
        self.assertIsNone(old_rule_prefix('Guizcore_-_Coffee_Time-WEB-FLAC-2026'))
