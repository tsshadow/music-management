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


def test_genre_less_fast_reading_without_strong_evidence_is_halved_and_not_reliable():
    choice = choose_octave(210.0, 1.0, Evidence(root='Soundcloud'), Scores(0.5, 0.45, None))
    assert choice.bpm == 105.0
    # Decided by the general priors alone: a guess, capped below reliable even at full pulse.
    assert choice.evidence == octave.EVIDENCE_NEUTRAL
    assert choice.confidence <= octave.WEAK_FOLD_CAP


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
