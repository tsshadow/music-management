"""Release folder names are told apart from label names (bug report 146).

Every name here is real: the polluting ones were labels in production LMS on 2026-10-02, the
others are record labels that must keep working, picked because they sit closest to the line --
"Free" in the name, a ` - ` in the name, an underscore in the name.
"""

import unittest

from services.common.label_names import looks_like_release_folder

#: Labels production LMS held that are really the release folder's name.
RELEASE_FOLDER_LABELS = (
    'STH685RMXBP - Bassjackers_-_I_Fink_U_Freeky_(Coone_Remix)-(STH685RMXBP)-SINGLE-WEB-2026-SRG',
    'K1R331 - Hakim_And_Lakesiders_-_Set_Me_Free-(K1R331)-SINGLE-WEB-2025-SRG',
    'ITAL050D - Zatox_-_The_Blaster_(Incl._Edit)-(ITAL050D)-WEB-2025-JUSTiFY_iNT',
    'MOK346 - VA_-_Area_303_-_Mokum_Acid_Special_3-(MOK346)-WEB-FLAC-2026',
    'ROTC23 DJ_Paul_-_The_Nightmare_Series-(ROTC23)-CD-1999',
)

#: Real labels, which must never be mistaken for one.
REAL_LABELS = (
    'DWX Copyright Free',
    'Freestyle',
    'Free For All',
    'Musical Freedom',
    'I AM HARDSTYLE - Amplify',
    '24 - 7 Hardcore',
    'Rude_Records',
    'Chosen_Few_Recordz',
    'ABSLT Records',
)


class LooksLikeReleaseFolderTest(unittest.TestCase):
    def test_release_folder_names_are_recognised(self):
        for name in RELEASE_FOLDER_LABELS:
            with self.subTest(name=name):
                self.assertTrue(looks_like_release_folder(name))

    def test_real_labels_are_not(self):
        for name in REAL_LABELS:
            with self.subTest(name=name):
                self.assertFalse(looks_like_release_folder(name))

    def test_nothing_is_not_a_release(self):
        for value in ('', '   ', None, 42):
            with self.subTest(value=value):
                self.assertFalse(looks_like_release_folder(value))


if __name__ == '__main__':
    unittest.main()
