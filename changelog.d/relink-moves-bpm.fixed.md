- A retag that changed a track's title, artist or duration lost its measured and its hand-corrected BPM: the relink to the new track row moved ratings, listens and the ml-analyzer rows, but not `library_track_bpm` and `library_track_bpm_manual`, which are keyed on the old `track_uid`. Both now move with the track; a value the new track already has is kept.

<!-- release notes -->

- Changing a track's tags no longer loses its BPM, measured or set by hand.
