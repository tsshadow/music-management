"""Which recordings are the same song, and which only look like it.

Pure functions, no database: the grouping rule is pinned down here so the worker
only has to be right about SQL.
"""

import unittest

from services.music_manager.song_versions import (
    KIND_ORDER,
    LONG_FORM_SECONDS,
    RANKING_VERSION,
    SPLIT_PREFIX,
    UNGROUPABLE_PREFIX,
    derived_bitrate,
    format_tier,
    is_official_release,
    ranking_signature,
    version_free_title,
    version_kind,
    version_score,
    work_key,
)


class VersionFreeTitleTest(unittest.TestCase):
    def test_length_variants_of_one_recording_collapse(self):
        titles = [
            'Raise Your Fist',
            'Raise Your Fist (Radio Edit)',
            'Raise Your Fist (Extended Mix)',
            'Raise Your Fist (Original Mix)',
            'Raise Your Fist (Official Video)',
            'Raise Your Fist [Free Download]',
        ]
        results = {version_free_title(title) for title in titles}
        self.assertEqual(len(results), 1, results)

    def test_a_remix_keeps_its_bracket(self):
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Wildstylez Remix)'),
            version_free_title('Raise Your Fist'),
        )

    def test_a_named_edit_is_not_a_radio_edit(self):
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Wildstylez Edit)'),
            version_free_title('Raise Your Fist (Radio Edit)'),
        )

    def test_a_bootleg_stays_its_own_song(self):
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Bootleg)'),
            version_free_title('Raise Your Fist'),
        )

    def test_a_bracket_that_is_part_of_the_title_survives(self):
        self.assertEqual(
            version_free_title('Raise Your Fist (Part 1)'),
            version_free_title('Raise Your Fist (Part 1)'),
        )
        self.assertNotEqual(
            version_free_title('Raise Your Fist (Part 1)'),
            version_free_title('Raise Your Fist'),
        )

    def test_two_stacked_markers_both_go(self):
        self.assertEqual(
            version_free_title('Raise Your Fist (Radio Edit) (Remastered)'),
            version_free_title('Raise Your Fist'),
        )

    def test_the_result_is_normalized(self):
        self.assertEqual(
            version_free_title('  Raise   Your Fist!  (Radio Edit)'),
            version_free_title('raise your fist'),
        )

    def test_an_empty_title_is_empty(self):
        self.assertEqual(version_free_title(None), '')
        self.assertEqual(version_free_title(''), '')


class VersionKindTest(unittest.TestCase):
    def test_radio_beats_edit_when_both_words_are_present(self):
        self.assertEqual(version_kind('Raise Your Fist (Radio Edit)'), 'radio')

    def test_extended_is_recognised(self):
        self.assertEqual(version_kind('Raise Your Fist (Extended Mix)'), 'extended')

    def test_original_is_recognised(self):
        self.assertEqual(version_kind('Raise Your Fist (Original Mix)'), 'original')

    def test_a_bare_edit_is_an_edit(self):
        self.assertEqual(version_kind('Raise Your Fist (Edit)'), 'edit')

    def test_instrumental_wins_over_everything_because_it_must_never_be_canonical(self):
        self.assertEqual(version_kind('Raise Your Fist (Radio Instrumental)'), 'instrumental')

    def test_no_marker_at_all_is_none(self):
        self.assertEqual(version_kind('Raise Your Fist'), 'none')

    def test_an_official_video_is_a_video(self):
        self.assertEqual(version_kind('Raise Your Fist (Official Video)'), 'video')

    def test_every_screen_upload_is_a_video(self):
        for title in (
            'Raise Your Fist (Official Music Video)',
            'Raise Your Fist [Videoclip]',
            'Raise Your Fist (Visualizer)',
            'Raise Your Fist (Official Audio)',
            'Raise Your Fist (Lyric Video)',
        ):
            self.assertEqual(version_kind(title), 'video', title)

    def test_a_video_of_the_radio_edit_is_still_a_video(self):
        self.assertEqual(version_kind('Raise Your Fist (Radio Edit) [Official Video]'), 'video')

    def test_a_pro_edit_and_a_pro_mix_are_pro(self):
        self.assertEqual(version_kind('Raise Your Fist (Pro Edit)'), 'pro')
        self.assertEqual(version_kind('Raise Your Fist (Pro Mix)'), 'pro')
        self.assertEqual(version_kind('Raise Your Fist (Pro-Mix)'), 'pro')

    def test_pro_and_music_video_group_with_the_song_and_keep_their_kind(self):
        # Bug report 098 taught the grouping key these words: a pro edit and a music video
        # now share the song's work, and the kind still tells them apart for the ranking.
        self.assertEqual(version_free_title('Raise Your Fist (Pro Edit)'), 'raise your fist')
        self.assertEqual(version_free_title('Raise Your Fist (Official Music Video)'), 'raise your fist')
        self.assertEqual(version_kind('Raise Your Fist (Pro Edit)'), 'pro')
        self.assertEqual(version_kind('Raise Your Fist (Official Music Video)'), 'video')

    def test_a_name_in_the_bracket_is_still_no_kind(self):
        self.assertEqual(version_kind('Raise Your Fist (Promo Edit By Wildstylez)'), 'none')

    def test_a_remix_is_none_because_it_is_a_song_of_its_own(self):
        self.assertEqual(version_kind('Raise Your Fist (Wildstylez Remix)'), 'none')

    def test_every_kind_appears_in_the_ranking_order(self):
        kinds = {'pro', 'radio', 'edit', 'original', 'none', 'extended', 'instrumental', 'video'}
        self.assertEqual(set(KIND_ORDER), kinds)

    def test_the_kind_order_is_the_one_teun_decided(self):
        # docs/designs/song-versions/functional.md: pro > radio > edit > original > none >
        # extended > instrumental > video.
        self.assertEqual(KIND_ORDER, ('pro', 'radio', 'edit', 'original', 'none', 'extended', 'instrumental', 'video'))


class WorkKeyTest(unittest.TestCase):
    def test_the_same_song_by_the_same_artist_shares_a_key(self):
        # Two different tracks, so the ids differ and must not reach the key.
        self.assertEqual(
            work_key('Angerfist', 'Raise Your Fist (Radio Edit)', 1, 214.0, None),
            work_key('angerfist', 'Raise Your Fist (Extended Mix)', 2, 337.0, None),
        )

    def test_a_different_artist_is_a_different_work(self):
        self.assertNotEqual(
            work_key('Angerfist', 'Raise Your Fist', 1, None, None),
            work_key('Radical Redemption', 'Raise Your Fist', 2, None, None),
        )

    def test_no_artist_still_groups_by_title(self):
        # Half this library has no primary_artist_id and carries the artist in the
        # title instead. Those versions still have to meet.
        self.assertEqual(
            work_key(None, 'The Elite - Royals (Radio Edit)', 1, 198.0, None),
            work_key(None, 'The Elite - Royals (Extended)', 2, 402.0, None),
        )

    def test_the_key_fits_the_column(self):
        key = work_key('A' * 300, 'B' * 300, 1, None, None)
        self.assertLessEqual(len(key), 191)


class UnusableTitleTest(unittest.TestCase):
    """A title that normalizes away identifies nothing, so it groups nothing.

    Production had 117 unrelated recordings in one work because every one of these
    titles produced the key ':::'.
    """

    UNUSABLE = ('', None, '   ', '🕊', '？', '᳄᳄᳄᳄᳆᳇᳇', '(Radio Edit)', '[Free Download]')

    def test_each_unusable_title_gets_a_key_of_its_own(self):
        for index, title in enumerate(self.UNUSABLE):
            with self.subTest(title=title):
                self.assertEqual(version_free_title(title), '')
                self.assertNotEqual(
                    work_key(None, title, index, None, None),
                    work_key(None, title, index + 100, None, None),
                )

    def test_two_unusable_titles_never_meet(self):
        keys = {work_key(None, title, index, None, None) for index, title in enumerate(self.UNUSABLE)}
        self.assertEqual(len(keys), len(self.UNUSABLE))

    def test_the_same_track_keeps_the_same_key(self):
        # The worker reads the key twice per pass and the repair script recomputes it
        # later; a key that moved would create a second work for one track.
        self.assertEqual(work_key(None, '', 77, None, None), work_key(None, None, 77, None, None))

    def test_an_unusable_title_is_marked_as_such(self):
        # Phase two has to be able to say why a song has one version: because nobody
        # else matched, or because the title was unusable. The namespace carries that.
        self.assertTrue(work_key('Angerfist', '', 77, None, None).startswith(UNGROUPABLE_PREFIX))
        self.assertFalse(work_key('Angerfist', 'Raise Your Fist', 77, None, None).startswith(UNGROUPABLE_PREFIX))

    def test_the_reserved_namespaces_cannot_collide_with_a_real_key(self):
        # Both mean "one track, and not because the song has one version". A real key
        # always carries the separator; neither prefix does.
        self.assertNotIn(':::', UNGROUPABLE_PREFIX)
        self.assertNotIn(':::', SPLIT_PREFIX)
        self.assertNotEqual(UNGROUPABLE_PREFIX, SPLIT_PREFIX)
        self.assertIn(':::', work_key('Angerfist', 'Raise Your Fist', 1, None, None))


class LongFormTest(unittest.TestCase):
    """A set or a radio episode is not a version of anything.

    Production grouped 16 hour-long episodes of "Andromedha Guest Mix" as one song,
    and 14 of "The Boom Room". A canonical filter over that hides a year of a weekly
    show behind one episode.
    """

    EPISODE = 'Andromedha Guest Mix'

    def test_two_episodes_of_one_show_are_two_works(self):
        self.assertNotEqual(
            work_key(None, self.EPISODE, 1, 3560.2, None),
            work_key(None, self.EPISODE, 2, 3629.4, None),
        )

    def test_a_long_recording_is_marked_ungroupable_rather_than_keyed_on_its_title(self):
        self.assertTrue(work_key(None, self.EPISODE, 1, 3560.2, None).startswith(UNGROUPABLE_PREFIX))

    def test_a_normal_song_of_the_same_name_still_groups(self):
        self.assertEqual(
            work_key('Angerfist', 'Raise Your Fist', 1, 214.0, None),
            work_key('Angerfist', 'Raise Your Fist (Radio Edit)', 2, 198.0, None),
        )

    def test_the_threshold_is_exclusive(self):
        # Sitting exactly on it groups; the band around it is empty in this library
        # anyway, so this is about the rule being decidable, not about the value.
        self.assertNotIn(UNGROUPABLE_PREFIX, work_key('Angerfist', 'Live At Defqon', 1, float(LONG_FORM_SECONDS), None))
        self.assertTrue(
            work_key('Angerfist', 'Live At Defqon', 1, LONG_FORM_SECONDS + 0.1, None).startswith(UNGROUPABLE_PREFIX)
        )

    def test_an_unknown_duration_groups_as_before(self):
        # duration_secs is nullable, and a track that never got a duration must not
        # be pushed into a work of its own for the lack of one.
        self.assertEqual(
            work_key('Angerfist', 'Raise Your Fist', 1, None, None),
            work_key('Angerfist', 'Raise Your Fist', 2, 0, None),
        )


class DerivedBitrateTest(unittest.TestCase):
    def test_a_320k_file_reads_as_320ish(self):
        # 320 kbit/s over 300 seconds is 12 MB.
        self.assertGreaterEqual(derived_bitrate(12_000_000, 300.0), 300)

    def test_a_192k_file_reads_as_192ish(self):
        self.assertLess(derived_bitrate(7_200_000, 300.0), 250)

    def test_a_missing_duration_is_zero_rather_than_a_crash(self):
        self.assertEqual(derived_bitrate(12_000_000, None), 0)
        self.assertEqual(derived_bitrate(12_000_000, 0.0), 0)

    def test_a_missing_size_is_zero(self):
        self.assertEqual(derived_bitrate(None, 300.0), 0)


class FormatTierTest(unittest.TestCase):
    def test_flac_outranks_every_lossy_format(self):
        self.assertLess(format_tier('a.flac', 1000), format_tier('a.mp3', 320))
        self.assertLess(format_tier('a.flac', 1000), format_tier('a.m4a', 256))

    def test_a_320_mp3_outranks_a_192_mp3(self):
        self.assertLess(format_tier('a.mp3', 320), format_tier('a.mp3', 192))

    def test_the_extension_is_case_insensitive(self):
        self.assertEqual(format_tier('a.FLAC', 1000), format_tier('a.flac', 1000))

    def test_the_lossless_order_in_full(self):
        order = [
            format_tier('a.flac', 1000),
            format_tier('a.wav', 1411),
            format_tier('a.mp3', 320),
            format_tier('a.m4a', 256),
            format_tier('a.mp3', 192),
            format_tier('a.mp3', 128),
        ]
        self.assertEqual(order, [0, 0, 1, 2, 3, 4])

    def test_the_storage_order_puts_mp3_320_first_and_lossless_after_aac(self):
        order = [
            format_tier('a.mp3', 320, prefer_lossless=False),
            format_tier('a.m4a', 256, prefer_lossless=False),
            format_tier('a.flac', 1000, prefer_lossless=False),
            format_tier('a.mp3', 192, prefer_lossless=False),
            format_tier('a.mp3', 128, prefer_lossless=False),
        ]
        self.assertEqual(order, [0, 1, 2, 3, 4])

    def test_a_lossless_file_is_never_mistaken_for_an_mp3_320_by_its_bitrate(self):
        # A FLAC reads around 1000 kbps; without the extension check first it would pass
        # the >= 300 test and land in the MP3 320 tier under the storage setting.
        self.assertEqual(format_tier('a.flac', 1000, prefer_lossless=False), 2)


class OfficialReleaseTest(unittest.TestCase):
    ROOTS = ('/mnt/music/EPs',)

    def test_a_file_in_the_label_tree_is_official_without_a_label(self):
        self.assertTrue(is_official_release('/mnt/music/EPs/Scantraxx/SCAN1/a.flac', False, False, self.ROOTS))

    def test_a_release_waiting_in_the_import_queue_is_official(self):
        # Hysta & RDO - TOGETHER: in EPs/__TODO, no label yet, lost to a SoundCloud rip.
        self.assertTrue(is_official_release('/mnt/music/EPs/__TODO/TOGETHER/a.flac', False, False, self.ROOTS))

    def test_a_queue_outside_the_tree_counts_when_it_is_listed(self):
        roots = ('/mnt/music/EPs', '/mnt/music/Import')
        self.assertTrue(is_official_release('/mnt/music/Import/x/a.flac', False, False, roots))

    def test_a_folder_that_only_starts_like_the_root_does_not_count(self):
        self.assertFalse(is_official_release('/mnt/music/EPs-old/a.flac', False, False, self.ROOTS))

    def test_a_labelled_file_outside_the_tree_is_official_unless_downloaded(self):
        self.assertTrue(is_official_release('/mnt/music/Lidarr/a.flac', True, False, self.ROOTS))
        self.assertFalse(is_official_release('/mnt/music/Soundcloud/a.mp3', True, True, self.ROOTS))

    def test_nothing_known_is_not_official(self):
        self.assertFalse(is_official_release(None, False, False, self.ROOTS))
        self.assertFalse(is_official_release('/mnt/music/Youtube/a.m4a', False, False, ()))


class RankingSignatureTest(unittest.TestCase):
    def test_the_setting_is_part_of_the_signature(self):
        self.assertNotEqual(ranking_signature(True), ranking_signature(False))

    def test_the_version_is_part_of_the_signature(self):
        self.assertTrue(ranking_signature(True).startswith(f'v{RANKING_VERSION}-'))


def _score(kind, path, kbps, official=False, lossless=True):
    return version_score(kind, path, kbps, is_official=official, prefer_lossless=lossless)


class VersionScoreTest(unittest.TestCase):
    """The ranking table, both settings. Each case: (winner, loser, why)."""

    LOSSLESS_CASES = (
        (('radio', 'a.flac', 1000), ('radio', 'b.mp3', 320), 'format first: flac beats mp3 320'),
        (('extended', 'a.flac', 1000), ('radio', 'b.mp3', 320), 'format before kind'),
        (('radio', 'a.mp3', 320), ('pro', 'b.m4a', 256), 'mp3 320 beats aac whatever the kind'),
        (('none', 'a.m4a', 128), ('radio', 'b.mp3', 128), 'aac beats a low mp3'),
        (('pro', 'a.flac', 1000), ('radio', 'b.flac', 1000), 'pro edit beats radio edit'),
        (('radio', 'a.flac', 1000), ('edit', 'b.flac', 1000), 'radio beats edit'),
        (('edit', 'a.flac', 1000), ('original', 'b.flac', 1000), 'edit beats original'),
        (('original', 'a.flac', 1000), ('none', 'b.flac', 1000), 'original beats unmarked'),
        (('none', 'a.flac', 1000), ('extended', 'b.flac', 1000), 'unmarked beats extended'),
        (('extended', 'a.flac', 1000), ('instrumental', 'b.flac', 1000), 'extended beats instrumental'),
        (('instrumental', 'a.flac', 1000), ('video', 'b.flac', 1000), 'a video is last'),
        (('radio', 'a.mp3', 256), ('radio', 'b.mp3', 192), 'within a tier the bitrate decides'),
    )

    LOSSY_CASES = (
        (('radio', 'a.mp3', 320), ('radio', 'b.flac', 1000), 'storage: mp3 320 beats flac'),
        (('radio', 'a.m4a', 256), ('radio', 'b.flac', 1000), 'storage: aac beats flac'),
        (('radio', 'a.flac', 1000), ('radio', 'b.mp3', 192), 'storage: flac still beats a low mp3'),
        (('extended', 'a.mp3', 320), ('pro', 'b.flac', 1000), 'storage: format before kind'),
        (('pro', 'a.mp3', 320), ('radio', 'b.mp3', 320), 'storage: pro beats radio'),
    )

    def test_the_lossless_ranking_table(self):
        for winner, loser, why in self.LOSSLESS_CASES:
            self.assertGreater(_score(*winner), _score(*loser), why)

    def test_the_storage_ranking_table(self):
        for winner, loser, why in self.LOSSY_CASES:
            self.assertGreater(_score(*winner, lossless=False), _score(*loser, lossless=False), why)

    def test_an_official_release_breaks_a_tie_the_bitrate_leaves(self):
        self.assertGreater(_score('radio', 'a.mp3', 322, official=True), _score('radio', 'b.mp3', 330))

    def test_container_overhead_does_not_outvote_the_official_release(self):
        # A 320 with a large embedded cover reads a few kbps higher; the 32 kbps step keeps
        # that from beating the official file.
        self.assertGreater(_score('radio', 'a.mp3', 321, official=True), _score('radio', 'b.mp3', 351))

    def test_a_real_bitrate_step_beats_official(self):
        self.assertGreater(_score('radio', 'a.mp3', 256), _score('radio', 'b.mp3', 192, official=True))

    def test_a_proper_release_beats_a_rip_of_the_same_edit(self):
        # The case this change exists for: the FLAC in EPs/ over the SoundCloud rip.
        self.assertGreater(_score('radio', 'a.flac', 900, official=True), _score('radio', 'b.mp3', 128))

    def test_an_unknown_kind_does_not_crash_and_ranks_as_none(self):
        self.assertEqual(_score('nonsense', 'a.flac', 1000), _score('none', 'a.flac', 1000))

    def test_the_largest_score_fits_a_signed_int_column(self):
        self.assertLess(_score('pro', 'a.flac', 10_000_000, official=True), 2**31 - 1)

    def test_a_missing_bitrate_scores_without_crashing(self):
        self.assertIsInstance(_score('none', '', 0), int)


class NonMusicWorkKeyTest(unittest.TestCase):
    """docs/designs/non-music-forms/: talk never groups with anything."""

    def test_an_interview_gets_a_key_of_its_own(self):
        self.assertEqual(work_key(None, 'QAPITAL 2019 Interview', 5, 300.0, 'interview'), f'{UNGROUPABLE_PREFIX}5')
        self.assertNotEqual(
            work_key(None, 'QAPITAL 2019 Interview', 5, 300.0, 'interview'),
            work_key(None, 'QAPITAL 2019 Interview', 6, 300.0, 'interview'),
        )

    def test_a_dvd_preview_gets_a_key_of_its_own(self):
        self.assertTrue(work_key('Zatox', 'DVD Preview', 8, 2122.0, 'preview').startswith(UNGROUPABLE_PREFIX))

    def test_a_music_form_groups_as_before(self):
        self.assertEqual(
            work_key('Angerfist', 'Raise Your Fist', 1, 214.0, 'track'),
            work_key('Angerfist', 'Raise Your Fist (Radio Edit)', 2, 198.0, None),
        )
