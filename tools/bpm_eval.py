"""Compare tempo estimators against tracks whose BPM tag is known to be genuine.

docs/designs/bpm-browse/technical.md, "Choosing the estimator". Not part of CI and never
run against production data in place: point it at a local copy of a sample of files.

Input is a TSV with one track per line -- `tag  old_tempo  genre  duration  path` -- where
`tag` is a trusted integer BPM (the evaluation used tags that are *off* the old librosa
lag grid, so they cannot have been written by the old analyzer) and `path` is the path as
music-manager sees it (/mnt/music/...). `--root` replaces the /mnt/music prefix.

Every method is fed the same excerpt (`--excerpt` seconds starting at 30% of the track),
decoded by ffmpeg at the sample rate the method wants. Reported per method: accuracy
within +-0.5 and +-1 BPM, the octave-error rate (the estimate is within 1 BPM of twice or
half the tag), accuracy when an oracle picks the octave (the ceiling octave folding can
reach), and the median seconds per track for the analysis itself, decoding excluded.

    python tools/bpm_eval.py --tsv gt.tsv --root ~/sample --methods ours,essentia_multifeature
"""

from __future__ import annotations

import argparse
import csv
import multiprocessing
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

os.environ.setdefault('OMP_NUM_THREADS', '1')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from services.music_manager.bpm import bands, estimator  # noqa: E402

METHODS = (
    'ours',
    'ours_folded',
    'essentia_multifeature',
    'essentia_degara',
    'essentia_percival',
    'librosa_grid',
    'librosa_ibi',
)


def decode(path: str, offset: float, seconds: float, rate: int) -> np.ndarray:
    """Mono float32 samples of `seconds` from `offset`, at `rate`, through ffmpeg."""
    cmd = [
        'ffmpeg',
        '-nostdin',
        '-v',
        'error',
        '-ss',
        f'{offset:.2f}',
        '-t',
        f'{seconds:.2f}',
        '-i',
        path,
        '-ac',
        '1',
        '-ar',
        str(rate),
        '-f',
        'f32le',
        '-',
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, timeout=120).stdout
    return np.frombuffer(out, dtype=np.float32)


def run_method(
    method: str, path: str, offset: float, seconds: float, genre: str = '', extra: dict | None = None
) -> tuple[float | None, float]:
    """(bpm, analysis seconds) for one method on one excerpt; `extra` collects diagnostics."""
    extra = extra if extra is not None else {}
    if method in ('ours', 'ours_folded'):
        y = decode(path, offset, seconds, estimator.SAMPLE_RATE)
        started = time.perf_counter()
        found = estimator.estimate_bpm(y)
        took = time.perf_counter() - started
        if method == 'ours':
            return found.bpm, took
        folded = bands.fold_into_band(found.bpm, bands.band_for_genres(genre.split(';')))
        extra.update(
            raw=found.bpm,
            confidence=found.confidence,
            strength=found.strength,
            halves_agree=found.halves_agree,
            half_score=found.half_score,
            double_score=found.double_score,
            octave_corrected=folded.octave_corrected,
            default_band=folded.default_band,
        )
        return folded.bpm, took
    if method.startswith('essentia'):
        import essentia.standard as es  # pylint: disable=import-outside-toplevel

        y = decode(path, offset, seconds, 44100)
        started = time.perf_counter()
        if method == 'essentia_percival':
            bpm = float(es.PercivalBpmEstimator()(y))
        else:
            algo = es.RhythmExtractor2013(method='multifeature' if method.endswith('multifeature') else 'degara')
            bpm = float(algo(y)[0])
        return bpm, time.perf_counter() - started
    import librosa  # pylint: disable=import-outside-toplevel

    y = decode(path, offset, seconds, 22050)
    started = time.perf_counter()
    if method == 'librosa_grid':
        tempo, _ = librosa.beat.beat_track(y=y, sr=22050)
        bpm = float(np.asarray(tempo).reshape(-1)[0])
    else:
        _, beats = librosa.beat.beat_track(y=y, sr=22050, hop_length=128, units='time')
        bpm = 60.0 / float(np.median(np.diff(beats))) if len(beats) > 2 else None
    return bpm, time.perf_counter() - started


def evaluate_track(args: tuple) -> dict:
    """All methods on one track; errors become a None estimate."""
    row, root, methods, seconds = args
    path = row['path'].replace('/mnt/music', root, 1)
    duration = float(row['duration'] or 0) or 240.0
    offset = max(0.0, min(duration * 0.3, duration - seconds))
    result = {'tag': float(row['tag']), 'old_tempo': row['old_tempo'], 'genre': row['genre'], 'path': row['path']}
    for method in methods:
        try:
            extra: dict = {}
            bpm, took = run_method(method, path, offset, seconds, row.get('genre') or '', extra)
            result.update({f'{method}_{key}': value for key, value in extra.items()})
        except Exception as exc:  # pylint: disable=broad-except  # one bad file must not end the run
            bpm, took = None, None
            result[f'{method}_error'] = str(exc)[:120]
        result[method] = bpm
        result[f'{method}_secs'] = took
    return result


def summarize(results: list[dict], methods: list[str]) -> list[dict]:
    """The comparison table: one row per method."""
    table = []
    for method in methods:
        n = hit05 = hit1 = octave = oracle = failed = 0
        secs = []
        for r in results:
            tag, est = r['tag'], r.get(method)
            n += 1
            if est is None:
                failed += 1
                continue
            secs.append(r[f'{method}_secs'])
            if abs(est - tag) <= 0.5:
                hit05 += 1
            if abs(est - tag) <= 1.0:
                hit1 += 1
            elif abs(est * 2 - tag) <= 2.0 or abs(est / 2 - tag) <= 1.0:
                octave += 1
            folded = est
            while folded < tag / 1.414:
                folded *= 2
            while folded > tag * 1.414:
                folded /= 2
            if abs(folded - tag) <= 1.0:
                oracle += 1
        table.append(
            {
                'method': method,
                'tracks': n,
                'within_0.5': f'{100 * hit05 / n:.1f}%',
                'within_1': f'{100 * hit1 / n:.1f}%',
                'octave_errors': f'{100 * octave / n:.1f}%',
                'within_1_oracle_octave': f'{100 * oracle / n:.1f}%',
                'failed': failed,
                'median_secs': f'{statistics.median(secs):.3f}' if secs else '-',
            }
        )
    return table


def main() -> None:
    """Parse arguments, evaluate in parallel, write the per-track CSV and print the table."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tsv', required=True)
    parser.add_argument('--root', required=True, help='replaces /mnt/music in the paths')
    parser.add_argument('--methods', default=','.join(METHODS))
    parser.add_argument('--excerpt', type=float, default=60.0)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--out', default='bpm_eval_results.csv')
    args = parser.parse_args()
    methods = [m for m in args.methods.split(',') if m]
    with open(args.tsv, encoding='utf-8') as handle:
        rows = [
            dict(zip(('tag', 'old_tempo', 'genre', 'duration', 'path'), line.rstrip('\n').split('\t'), strict=False))
            for line in handle
            if line.strip()
        ]
    rows = [r for r in rows if os.path.exists(r['path'].replace('/mnt/music', args.root, 1))]
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(max_workers=args.jobs, mp_context=context, max_tasks_per_child=25) as pool:
        results = list(pool.map(evaluate_track, [(r, args.root, methods, args.excerpt) for r in rows]))
    with open(args.out, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted({k for r in results for k in r}))
        writer.writeheader()
        writer.writerows(results)
    table = summarize(results, methods)
    columns = list(table[0])
    print(' | '.join(columns))
    for row in table:
        print(' | '.join(str(row[c]) for c in columns))


if __name__ == '__main__':
    main()
