"""The octave choice (bug report 140): T/2, T or 2T, weighed on priors, path and comb scores.

The cases are production's: André Hazes's ballads doubled to 256 through his artist's hardstyle
remixes, The Silence's "Nothing" doubled to 230 by the industrial hardcore band, a pop song in the
Spotify folder read at 234, and a genre-less uptempo track that must keep its 215. The learned
priors below are the values production's data gave on 2026-09-30.
"""

import math

import pytest

from services.music_manager.bpm import octave
from services.music_manager.bpm.octave import Evidence, Prior, Scores, choose_octave

#: Learned genre priors as production has them (centre log2 BPM, spread, samples).
GENRES = {
    'hardstyle': Prior(7.2687, 0.0479, 26903),
    'hardcore': Prior(7.5616, 0.1410, 23198),
    'industrial hardcore': Prior(7.4980, 0.1465, 948),
    'uptempo hardcore': Prior(7.6623, 0.0849, 7723),
    'dance': Prior(7.0969, 0.1526, 1435),
}
GENOSHA_RECORDS = Prior(7.3057, 0.1607, 65)
THE_SILENCE = Prior(7.1517, 0.1871, 15)


def test_andre_hazes_ballad_in_hitzone_is_128_not_256():
    """No genre of its own; the artist's profile came from remixes, which the priors leave out,
    so there is no artist prior; the Hitzone path and the neutral prior settle it."""
    choice = choose_octave(64.0, 1.0, Evidence(root='Hitzone', genre_priors=GENRES), Scores(0.5693, None, 0.4739))
    assert choice.bpm == 128.0
    assert choice.octave_corrected
    # Folded on the general priors alone: shown as 128, but not reliable (not written to the tag).
    assert choice.confidence <= octave.WEAK_FOLD_CAP


def test_andre_hazes_at_his_own_tempo_stays():
    choice = choose_octave(131.81, 1.0, Evidence(root='Hitzone', genre_priors=GENRES), Scores(0.4724, 0.467, None))
    assert choice.bpm == 131.81
    assert not choice.octave_corrected


def test_an_artist_prior_alone_never_folds_a_track_up_into_hard_dance():
    """Even a consistent uptempo artist prior may not double a genre-less 128 to 256."""
    evidence = Evidence(artist=Prior.around(250.0, 0.1, 40), genre_priors=GENRES)
    assert choose_octave(128.0, 0.9, evidence).bpm == 128.0


def test_a_genre_pure_label_may_fold_a_genre_less_track_up():
    """A terror label's genre-less 105 is a 210: labels here are genre-pure."""
    evidence = Evidence(label=Prior.around(210.0, 0.1, 200), genre_priors=GENRES)
    assert choose_octave(105.0, 0.9, evidence).bpm == 210.0


def test_the_silence_nothing_stays_at_its_slow_tempo():
    """Raw 115 with a clear pulse, genres Hardcore + Industrial Hardcore: the double scored 0.47 of
    the estimate, far below what a correct octave neighbour scores, so 115 stays -- confidently."""
    evidence = Evidence(
        genres=('Hardcore', 'Industrial Hardcore'),
        label=GENOSHA_RECORDS,
        artist=THE_SILENCE,
        genre_priors=GENRES,
    )
    choice = choose_octave(115.0, 0.956, evidence, Scores(0.3345, None, 0.15679))
    assert choice.bpm == 115.0
    assert choice.evidence == octave.EVIDENCE_ESTIMATE
    assert choice.confidence >= 0.75


def test_the_silence_without_comb_scores_stays_but_is_ambiguous():
    """A row from before the scores were stored: the priors alone keep 115, barely -- the worker
    re-measures it first to get the scores."""
    evidence = Evidence(
        genres=('Hardcore', 'Industrial Hardcore'),
        label=GENOSHA_RECORDS,
        artist=THE_SILENCE,
        genre_priors=GENRES,
    )
    choice = choose_octave(115.0, 0.97, evidence)
    assert choice.bpm == 115.0
    assert choice.ambiguous
    assert choice.confidence < 0.75


def test_genre_less_soundcloud_uptempo_with_a_strong_fast_pulse_stays():
    choice = choose_octave(215.0, 0.9, Evidence(root='Soundcloud'), Scores(0.5, 0.25, None))
    assert choice.bpm == 215.0


def test_genre_less_fast_reading_without_evidence_stays_unsettled_and_not_reliable():
    """Issue #153: the neutral prior alone halved 4,209 such tracks on production. Nothing real
    favours the half, so the estimate stays; nothing backs the estimate either, so it is a tie."""
    choice = choose_octave(210.0, 1.0, Evidence(root='Soundcloud'), Scores(0.5, 0.45, None))
    assert choice.bpm == 210.0
    assert not choice.octave_corrected
    assert choice.evidence == octave.EVIDENCE_UNSETTLED
    assert choice.ambiguous
    assert choice.confidence <= octave.WEAK_FOLD_CAP
    assert octave.weak_value(choice.octave_corrected, choice.evidence)


def test_genre_less_fast_reading_without_comb_scores_is_unsettled_too():
    choice = choose_octave(234.0, 0.95, Evidence(root='Youtube'))
    assert (choice.bpm, choice.evidence) == (234.0, octave.EVIDENCE_UNSETTLED)
    assert choice.confidence <= octave.WEAK_FOLD_CAP


@pytest.mark.parametrize(
    ('evidence', 'name'),
    [
        (Evidence(root='Soundcloud', artist=Prior.around(115.0, 0.15, 40)), octave.EVIDENCE_ARTIST),
        (Evidence(root='Soundcloud', label=Prior.around(110.0, 0.15, 200)), octave.EVIDENCE_LABEL),
        (Evidence(genres=('Dance',), genre_priors=GENRES), octave.EVIDENCE_GENRE),
        (Evidence(root='Soundcloud', folder=Prior.around(118.0, 0.15, 60)), octave.EVIDENCE_FOLDER),
    ],
)
def test_a_real_prior_on_the_half_still_halves_a_fast_reading(evidence, name):
    choice = choose_octave(230.0, 0.9, evidence, Scores(0.5, 0.45, None))
    assert choice.bpm == 115.0
    assert choice.octave_corrected
    assert choice.evidence in (name, octave.EVIDENCE_NEUTRAL)


def test_an_uploader_folder_settles_a_genre_less_fast_upload():
    """Issue #241: a Liquicity upload read at 348 with nothing else to go on is halved by its
    folder's 174; one from a hard-dance channel read at 234 keeps its estimate, settled."""
    liquid = Evidence(root='Youtube', folder=Prior.around(174.0, 0.08, 120))
    halved = choose_octave(348.0, 0.9, liquid, Scores(0.5, 0.45, None))
    assert (halved.bpm, halved.octave_corrected) == (174.0, True)
    assert not octave.weak_value(halved.octave_corrected, halved.evidence)

    fast = Evidence(root='Soundcloud', folder=Prior.around(230.0, 0.08, 120))
    kept = choose_octave(234.0, 0.9, fast, Scores(0.5, 0.45, None))
    assert (kept.bpm, kept.octave_corrected) == (234.0, False)
    assert kept.evidence != octave.EVIDENCE_UNSETTLED
    assert kept.confidence >= 0.75


def test_a_folder_prior_alone_never_folds_a_track_up_into_hard_dance():
    """Like an artist's: only the track's own genre, its label or GetSongBPM double past 205."""
    evidence = Evidence(root='Soundcloud', folder=Prior.around(250.0, 0.1, 400), genre_priors=GENRES)
    assert choose_octave(125.0, 0.9, evidence).bpm == 125.0


def test_a_thin_folder_prior_is_no_evidence_for_a_halving():
    choice = choose_octave(230.0, 0.9, Evidence(root='Soundcloud', folder=Prior.around(115.0, 0.15, 4)))
    assert (choice.bpm, choice.evidence) == (230.0, octave.EVIDENCE_UNSETTLED)


@pytest.mark.parametrize(
    ('path', 'key'),
    [
        ('/mnt/music/Soundcloud/Rebelion/track.mp3', 'soundcloud/rebelion'),
        ('/mnt/music/Youtube/Q-dance/2024/set.m4a', 'youtube/q-dance'),
        ('/mnt/music/SOUNDCLOUD/A B/c.mp3', 'soundcloud/a b'),
        ('/mnt/music/Soundcloud/loose.mp3', None),
        ('/mnt/music/EPs/Scantraxx/SCAN123/x.flac', None),
        ('/mnt/music/Soundcloud//x.mp3', None),
        ('/elsewhere/Soundcloud/Rebelion/x.mp3', None),
        (None, None),
    ],
)
def test_folder_key(path, key):
    assert octave.folder_key(path) == key


def test_a_folder_key_fits_the_prior_key_column():
    key = octave.folder_key('/mnt/music/Youtube/' + 'x' * 300 + '/t.mp3')
    assert key is not None and len(key) == octave.FOLDER_KEY_LENGTH


def test_a_thin_artist_prior_is_no_evidence_for_a_halving():
    """An artist with fewer than ARTIST_MIN_SAMPLES confident tracks says nothing."""
    choice = choose_octave(230.0, 0.9, Evidence(root='Soundcloud', artist=Prior.around(115.0, 0.15, 2)))
    assert (choice.bpm, choice.evidence) == (230.0, octave.EVIDENCE_UNSETTLED)


def test_an_artist_prior_on_the_fast_side_keeps_the_estimate_without_inflating_it():
    """The general priors favour the half, the artist the estimate: kept, but not made more certain
    than the scoring says -- the rule change must not make an old row reliable on its own."""
    evidence = Evidence(root='Soundcloud', artist=Prior.around(170.0, 0.4, 5))
    choice = choose_octave(230.0, 0.9, evidence, Scores(0.5, 0.45, None))
    assert (choice.bpm, choice.evidence) == (230.0, octave.EVIDENCE_UNSETTLED)
    assert choice.confidence <= octave.WEAK_FOLD_CAP


def test_a_clearly_weaker_half_pulse_settles_a_fast_estimate():
    choice = choose_octave(230.0, 0.9, Evidence(root='Soundcloud'), Scores(0.5, 0.2, None))
    assert choice.bpm == 230.0
    assert choice.evidence != octave.EVIDENCE_UNSETTLED
    assert not octave.weak_value(choice.octave_corrected, choice.evidence)


def test_weak_value_names_the_outcomes_the_writeback_skips():
    assert octave.weak_value(False, octave.EVIDENCE_UNSETTLED)
    assert octave.weak_value(True, octave.EVIDENCE_NEUTRAL)
    assert octave.weak_value(True, octave.EVIDENCE_PATH)
    assert not octave.weak_value(False, octave.EVIDENCE_NEUTRAL)  # the estimate itself, kept
    assert not octave.weak_value(True, octave.EVIDENCE_GENRE)
    assert not octave.weak_value(True, octave.EVIDENCE_ARTIST)
    assert not octave.weak_value(False, None)


def test_pop_in_the_spotify_folder_at_234_is_117():
    choice = choose_octave(234.0, 0.9, Evidence(root='Spotify'))
    assert choice.bpm == 117.0
    assert choice.evidence in (octave.EVIDENCE_PATH, octave.EVIDENCE_NEUTRAL)


def test_a_half_time_hardstyle_reading_is_doubled_by_its_genre():
    choice = choose_octave(75.0, 0.95, Evidence(genres=('Hardstyle',), genre_priors=GENRES))
    assert choice.bpm == 150.0
    assert choice.evidence == octave.EVIDENCE_GENRE
    assert not choice.ambiguous
    # A fold the track's own genre decided clearly can still be reliable.
    assert choice.confidence >= 0.75


def test_a_genre_less_half_time_reading_is_doubled_in_this_collection():
    assert choose_octave(87.0, 0.9, Evidence()).bpm == 174.0
    assert choose_octave(64.0, 0.9, Evidence()).bpm == 128.0


def test_a_genre_less_mid_tempo_stays():
    for raw in (100.0, 128.0, 160.0):
        assert choose_octave(raw, 0.9, Evidence()).bpm == raw


def test_a_genre_without_a_learned_prior_falls_back_to_its_band():
    choice = choose_octave(80.0, 0.9, Evidence(genres=('Happy Hardcore',)))
    assert choice.bpm == 160.0
    assert choice.evidence == octave.EVIDENCE_BAND


def test_the_most_specific_genre_decides():
    prior, _, kind = octave.genre_evidence(('Hardcore', 'Uptempo Hardcore'), GENRES)
    assert prior == GENRES['uptempo hardcore']
    assert kind == octave.EVIDENCE_GENRE


def test_a_thin_or_wide_learned_prior_is_ignored():
    assert octave.genre_evidence(('Hardstyle',), {'hardstyle': Prior(7.27, 0.05, 3)})[2] == octave.EVIDENCE_BAND
    wide_label = Evidence(label=Prior.around(210.0, 0.8, 500))
    assert choose_octave(105.0, 0.9, wide_label).bpm == 105.0


def test_candidates_stay_inside_40_to_500():
    assert choose_octave(45.0, 0.9, Evidence()).bpm in (45.0, 90.0)
    assert choose_octave(480.0, 0.9, Evidence(genres=('Speedcore',))).bpm in (480.0, 240.0)


def test_a_tie_halves_the_confidence_and_a_clear_win_keeps_it():
    assert choose_octave(150.0, 0.8, Evidence(genres=('Hardstyle',), genre_priors=GENRES)).confidence > 0.75
    tie = octave.Choice(bpm=1.0, factor=1.0, confidence=0.0, evidence='x', margin=0.0)
    assert tie.ambiguous
    assert math.isclose(1.0 - 0.5 * math.exp(-octave.CERTAINTY_RATE * 0.0), 0.5)


def test_no_raw_confidence_means_no_confidence():
    assert choose_octave(150.0, None).confidence == 0.0


@pytest.mark.parametrize(
    ('ratio', 'expected'),
    [(None, 0.0), (1.0, 0.0), (1.4, 0.0), (float('nan'), 0.0)],
)
def test_the_audio_term_is_zero_without_evidence_against(ratio, expected):
    assert octave.audio_term(ratio) == expected


def test_the_audio_term_bites_below_the_knee():
    assert octave.audio_term(0.8) > -0.5
    assert octave.audio_term(0.47) < -3.0


def test_band_prior_puts_the_band_edges_at_one_sigma():
    prior = octave.band_prior((135.0, 175.0))
    assert math.isclose(2**prior.centre, math.sqrt(135.0 * 175.0))
    assert math.isclose(prior.spread, math.log2(175.0 / 135.0) / 2)


@pytest.mark.parametrize(
    ('path', 'root'),
    [
        ('/mnt/music/Hitzone/Hitzone 33/CD/a.mp3', 'Hitzone'),
        ('/mnt/music/Top 100/x.mp3', 'Top 100'),
        ('/elsewhere/Soundcloud/x.mp3', 'elsewhere'),
        (None, None),
        ('', None),
    ],
)
def test_root_of(path, root):
    assert octave.root_of(path) == root


# ----------------------------------------------------------------------------- GetSongBPM (issue #152)


def _listed(bpm):
    """A GetSongBPM tempo as the evidence carries it."""
    return Prior.around(bpm, octave.EXTERNAL_SPREAD)


def test_a_listed_tempo_makes_the_hazes_fold_reliable():
    evidence = Evidence(root='Hitzone', genre_priors=GENRES, external=_listed(128.0))
    choice = choose_octave(64.0, 1.0, evidence, Scores(0.5693, None, 0.4739))
    assert (choice.bpm, choice.evidence, choice.external_bpm) == (128.0, octave.EVIDENCE_EXTERNAL, 128.0)
    assert choice.confidence >= 0.75


def test_a_listed_half_time_keeps_a_ballad_at_its_measured_octave():
    evidence = Evidence(root='Spotify', genre_priors=GENRES, external=_listed(72.0))
    choice = choose_octave(144.4, 0.9, evidence)
    assert choice.bpm == pytest.approx(72.2)
    assert choice.evidence == octave.EVIDENCE_EXTERNAL


def test_a_listed_tempo_near_no_octave_is_another_recording_and_ignored():
    evidence = Evidence(root='Hitzone', genre_priors=GENRES, external=_listed(100.0))
    with_it = choose_octave(64.0, 1.0, evidence, Scores(0.5693, None, 0.4739))
    without = choose_octave(64.0, 1.0, Evidence(root='Hitzone', genre_priors=GENRES), Scores(0.5693, None, 0.4739))
    assert with_it == without
    assert with_it.external_bpm is None


def test_a_listed_fast_tempo_vouches_for_a_doubling_above_the_limit():
    """Without it a genre-less 107 never doubles to 214; with GetSongBPM saying 214 it may."""
    plain = choose_octave(107.0, 0.9, Evidence(root='Spotify'))
    assert plain.bpm == 107.0
    listed = choose_octave(107.0, 0.9, Evidence(root='Spotify', external=_listed(214.0)))
    assert listed.bpm == 214.0


def test_weak_priors_means_a_mainstream_path_without_label_or_artist_prior():
    assert octave.weak_priors(Evidence(root='Hitzone'))
    assert octave.weak_priors(Evidence(root='top 100', artist=Prior.around(120, 0.2, 2)))  # too thin
    assert not octave.weak_priors(Evidence(root='Soundcloud'))
    assert not octave.weak_priors(Evidence(root='Lidarr', artist=Prior.around(120, 0.2, 40)))
    assert not octave.weak_priors(Evidence(root='Spotify', label=GENOSHA_RECORDS))
