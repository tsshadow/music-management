import os
import unittest
from tempfile import TemporaryDirectory

from services.importer.label_resolver import resolve


class LabelResolverTest(unittest.TestCase):
    """
    The label of a release the importer could not place is usually sitting in the
    release's own files. These tests pin down which tag wins, and which value is never
    a label however confidently it is tagged.

    The tags are injected rather than written into real audio files: the suite replaces
    the mutagen module wholesale (`services/tests/mock_base.py`), so nothing here could
    write a readable ID3 frame. What is exercised is the choosing, which is where the
    behaviour lives; `read_tags` itself is a ten-line flatten over mutagen's own output.
    """

    def setUp(self):
        # pylint does not know enterContext closes the directory at the end of the test.
        self.root = self.enterContext(TemporaryDirectory())  # pylint: disable=consider-using-with
        self.tags = {}

    def reader(self, path):
        return self.tags.get(path, {})

    def add_track(self, name, **tags):
        path = os.path.join(self.root, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('not really audio')
        self.tags[path] = tags
        return path

    def add_nfo(self, name, text):
        with open(os.path.join(self.root, name), 'w', encoding='utf-8') as handle:
            handle.write(text)

    def resolve(self, **kwargs):
        return resolve(self.root, tag_reader=self.reader, **kwargs)

    def test_the_id3_publisher_frame_is_proposed_as_the_label(self):
        self.add_track('one.mp3', tpub='Traxtorm Records')

        proposal = self.resolve()

        self.assertEqual(proposal.label, 'Traxtorm Records')
        self.assertEqual(proposal.source, 'tag:tpub')
        self.assertGreater(proposal.confidence, 0)

    def test_the_vorbis_label_field_beats_a_weaker_copyright(self):
        self.add_track('one.flac', label='Brutal Kuts', copyright='Fracus (2026)')

        proposal = self.resolve()

        self.assertEqual(proposal.label, 'Brutal Kuts')
        self.assertEqual(proposal.source, 'tag:label')

    def test_the_poisoned_import_folder_publisher_is_never_proposed(self):
        self.add_track('one.mp3', **{'txxx:publisher': '__TODO'})

        proposal = self.resolve(import_folder_name='__TODO')

        self.assertIsNone(proposal.label)
        self.assertEqual(proposal.source, 'none')

    def test_two_files_agreeing_raise_the_confidence(self):
        self.add_track('one.mp3', tpub='Brutal Kuts')
        self.add_track('two.mp3', tpub='Brutal Kuts')

        confidence_of_a_single_file = 80
        self.assertGreater(self.resolve().confidence, confidence_of_a_single_file)

    def test_the_value_most_files_agree_on_wins(self):
        self.add_track('one.mp3', tpub='Brutal Kuts')
        self.add_track('two.mp3', tpub='Brutal Kuts')
        self.add_track('three.mp3', tpub='Typo Records')

        self.assertEqual(self.resolve().label, 'Brutal Kuts')

    def test_a_folder_without_audio_yields_an_empty_proposal(self):
        proposal = self.resolve()

        self.assertIsNone(proposal.label)
        self.assertEqual(proposal.confidence, 0)

    def test_the_catalogue_number_in_a_tag_beats_the_one_in_the_folder_name(self):
        self.add_track('one.flac', label='Brutal Kuts', labelno='BKRP104')

        self.assertEqual(self.resolve(catid_from_name='WRONG').catid, 'BKRP104')

    def test_the_catalogue_number_from_the_folder_name_is_kept_when_no_tag_holds_one(self):
        self.add_track('one.mp3', tpub='Brutal Kuts')

        self.assertEqual(self.resolve(catid_from_name='BKRP104').catid, 'BKRP104')

    def test_the_nfo_is_read_when_no_tag_holds_a_label(self):
        self.add_track('one.mp3')
        self.add_nfo('release.nfo', 'Artist....: Darwin\nLabel.....: Brutal Kuts\nYear......: 2026\n')

        proposal = self.resolve()

        self.assertEqual(proposal.label, 'Brutal Kuts')
        self.assertEqual(proposal.source, 'nfo')

    def test_a_tagged_label_beats_the_nfo(self):
        self.add_track('one.mp3', tpub='Traxtorm Records')
        self.add_nfo('release.nfo', 'Label.....: Brutal Kuts\n')

        self.assertEqual(self.resolve().label, 'Traxtorm Records')

    def test_a_file_with_no_readable_tags_does_not_stop_the_resolution(self):
        # An unreadable file is what `read_tags` turns into an empty mapping.
        self.add_track('broken.mp3')
        self.add_track('two.mp3', tpub='Brutal Kuts')

        self.assertEqual(self.resolve().label, 'Brutal Kuts')


if __name__ == '__main__':
    unittest.main()
