"""Tempo per track, for browsing by BPM.

`bands` folds a tempo into the octave the track's genre plays in, `effective` decides which of a
track's BPM sources wins, and `index` holds the result in memory for the browse API
(routers/bpm.py). The measurement worker that fills `library_track_bpm` follows in its own
change. See docs/designs/bpm-browse/technical.md.
"""
