"""Tempo estimation with fractional precision, in plain numpy.

docs/designs/bpm-browse/technical.md, "Estimator". The BPM data this replaces came from
`librosa.beat.beat_track` at 22050 Hz / hop 512: its tempo is `60 * sr / (hop * lag)` for an
integer autocorrelation lag, so around 150 BPM the only values it can produce are 143.6,
152.0 and 161.5 -- a 150 and a 155 BPM track both read 152. This module keeps the
autocorrelation idea but removes the grid:

1. An onset envelope (log-magnitude spectral flux) at 11025 Hz with a 64-sample hop, i.e.
   172 frames a second.
2. Its autocorrelation, computed through the FFT.
3. For every candidate tempo on a 0.1 BPM grid (then 0.01 around the winner) the mean of the
   autocorrelation at the first `HARMONICS` whole multiples of the beat period, read with
   linear interpolation between lags. Summing over multiples is what buys the precision: an
   error of one frame in the period becomes `n` frames at the n-th multiple, so the peak of
   the sum is `HARMONICS` times sharper than any single lag.

It deliberately does not decide between octaves (75 vs 150 vs 300): the score of the half
and double tempo is returned alongside, and `bands.fold_into_band` settles it with the
track's genre. No librosa: its import alone costs ~150 MB of resident memory (scipy,
scikit-learn, numba) in a worker that is meant to stay small, and numpy's FFT is all this
needs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: The decode rate the estimator expects. Kick drums and hats, which carry the tempo in
#: dance music, sit well below the 5.5 kHz this keeps; halving 22050 halves the work.
SAMPLE_RATE = 11025
N_FFT = 512
HOP = 64
#: Onset-envelope frames per second.
FPS = SAMPLE_RATE / HOP

#: The raw search range. Octave folding into a genre's band happens afterwards.
MIN_BPM = 60.0
MAX_BPM = 250.0
COARSE_STEP = 0.1
FINE_STEP = 0.01
#: How many whole multiples of the beat period are averaged per candidate tempo.
HARMONICS = 12

#: Mean normalised autocorrelation at which a pulse counts as clearly periodic. On the
#: evaluation set (tools/bpm_eval.py) correct estimates had a median strength of 0.45 and
#: wrong ones 0.34.
STRONG_PULSE = 0.35
#: Stored in `library_track_bpm.method`; bump it when the algorithm changes to re-measure.
METHOD = 'acf-comb-v1'
#: Below this many seconds of audio there is too little to measure a tempo from.
MIN_SECONDS = 8.0


@dataclass(frozen=True)
class Estimate:
    """One measurement: the tempo, how sure we are, and what the octave neighbours scored.

    `bpm` is the raw winner in MIN_BPM..MAX_BPM, not yet folded into a genre band.
    `confidence` is 0..1: pulse strength, discounted when the two halves of the excerpt
    disagree. `half_score` / `double_score` are the scores of bpm/2 and bpm*2 (None when
    outside the search range), for the octave decision.
    """

    bpm: float
    confidence: float
    strength: float
    halves_agree: bool
    half_score: float | None
    double_score: float | None


class TooShort(ValueError):
    """The excerpt holds too little audio to estimate a tempo from."""


def onset_envelope(samples: np.ndarray) -> np.ndarray:
    """Log-magnitude spectral flux of mono `samples` at SAMPLE_RATE, one value per HOP."""
    y = np.asarray(samples, dtype=np.float32)
    if y.ndim != 1:
        y = y.mean(axis=0 if y.shape[0] < y.shape[-1] else 1).astype(np.float32)
    n_frames = 1 + (len(y) - N_FFT) // HOP
    if n_frames < 2:
        raise TooShort(f'{len(y)} samples')
    window = np.hanning(N_FFT).astype(np.float32)
    flux = np.empty(n_frames, dtype=np.float32)
    previous = None
    chunk = 4096
    # Chunked so a 90 s excerpt never holds its whole spectrogram (~20 MB) at once.
    for start in range(0, n_frames, chunk):
        stop = min(n_frames, start + chunk)
        idx = np.arange(start, stop)[:, None] * HOP + np.arange(N_FFT)[None, :]
        spectrum = np.abs(np.fft.rfft(y[idx] * window, axis=1)).astype(np.float32)
        log_mag = np.log1p(1000.0 * spectrum)
        if previous is None:
            diff = np.diff(log_mag, axis=0, prepend=log_mag[:1])
        else:
            diff = np.diff(log_mag, axis=0, prepend=previous[None, :])
        flux[start:stop] = np.maximum(diff, 0.0).sum(axis=1)
        previous = log_mag[-1]
    # High-pass: subtract a ~0.5 s moving average so slow loudness changes (a build-up,
    # a breakdown) do not dominate the autocorrelation, then half-wave rectify.
    width = max(1, int(FPS * 0.5))
    kernel = np.ones(width, dtype=np.float32) / width
    local = np.convolve(flux, kernel, mode='same')
    return np.maximum(flux - local, 0.0)


def autocorrelation(envelope: np.ndarray, max_lag: int) -> np.ndarray:
    """Normalised autocorrelation of `envelope` for lags 0..max_lag (ac[0] == 1)."""
    x = envelope.astype(np.float64) - float(envelope.mean())
    size = 1 << int(np.ceil(np.log2(len(x) + max_lag + 1)))
    spectrum = np.fft.rfft(x, size)
    ac = np.fft.irfft(spectrum * np.conj(spectrum), size)[: max_lag + 1]
    if ac[0] <= 0:
        return np.zeros(max_lag + 1)
    return ac / ac[0]


def tempo_scores(ac: np.ndarray, bpms: np.ndarray, harmonics: int = HARMONICS) -> np.ndarray:
    """Per candidate tempo: the mean autocorrelation at its first `harmonics` beat multiples."""
    lags = FPS * 60.0 / np.asarray(bpms, dtype=np.float64)
    max_lag = len(ac) - 1
    total = np.zeros_like(lags)
    count = np.zeros_like(lags)
    positions = np.arange(len(ac), dtype=np.float64)
    for n in range(1, harmonics + 1):
        at = n * lags
        inside = at <= max_lag
        total[inside] += np.interp(at[inside], positions, ac)
        count[inside] += 1
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(count > 0, total / np.maximum(count, 1), 0.0)


def _best_tempo(envelope: np.ndarray) -> tuple[float, float, np.ndarray]:
    """(bpm, score, ac) of the strongest tempo in MIN_BPM..MAX_BPM for one envelope."""
    max_lag = int(np.ceil(HARMONICS * FPS * 60.0 / MIN_BPM)) + 2
    max_lag = min(max_lag, len(envelope) - 1)
    ac = autocorrelation(envelope, max_lag)
    coarse = np.arange(MIN_BPM, MAX_BPM + COARSE_STEP / 2, COARSE_STEP)
    scores = tempo_scores(ac, coarse)
    best = float(coarse[int(np.argmax(scores))])
    fine = np.arange(max(MIN_BPM, best - 0.3), min(MAX_BPM, best + 0.3) + FINE_STEP / 2, FINE_STEP)
    fine_scores = tempo_scores(ac, fine)
    index = int(np.argmax(fine_scores))
    return float(fine[index]), float(fine_scores[index]), ac


def _score_at(ac: np.ndarray, bpm: float) -> float | None:
    """The score of one tempo, or None outside the search range."""
    if bpm < MIN_BPM or bpm > MAX_BPM:
        return None
    return float(tempo_scores(ac, np.array([bpm]))[0])


def estimate_bpm(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Estimate:
    """Estimate the tempo of mono `samples` (float, at SAMPLE_RATE).

    Raises TooShort for less than MIN_SECONDS of audio and ValueError for a wrong rate --
    resampling is the decoder's job (ffmpeg does it for free while decoding).
    """
    if sample_rate != SAMPLE_RATE:
        raise ValueError(f'expected {SAMPLE_RATE} Hz, got {sample_rate}')
    if len(samples) < MIN_SECONDS * SAMPLE_RATE:
        raise TooShort(f'{len(samples) / SAMPLE_RATE:.1f}s of audio')
    envelope = onset_envelope(samples)
    bpm, strength, ac = _best_tempo(envelope)

    half = len(envelope) // 2
    halves_agree = True
    if half / FPS >= MIN_SECONDS:
        first, _, _ = _best_tempo(envelope[:half])
        second, _, _ = _best_tempo(envelope[half:])
        halves_agree = abs(first - second) <= 1.0 and abs(first - bpm) <= 1.5

    confidence = min(1.0, max(0.0, strength / STRONG_PULSE))
    if not halves_agree:
        confidence *= 0.5
    return Estimate(
        bpm=round(bpm, 2),
        confidence=round(confidence, 3),
        strength=round(strength, 4),
        halves_agree=halves_agree,
        half_score=_score_at(ac, bpm / 2),
        double_score=_score_at(ac, bpm * 2),
    )
