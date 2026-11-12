- **A Soundcloud or YouTube upload's octave now also follows its uploader folder.** Each uploader
  folder (`Soundcloud/<uploader>`, `Youtube/<channel>`) has a tempo prior learned from the
  confident measurements of its uploads, weighted like an artist's, with the track itself left out.
  It counts as real evidence for halving a reading above 205 BPM, but never doubles a track past
  205 on its own. 98.9% of the uploads have one, against 69.4% with an artist prior. A dry run on
  production's rows settles 2,774 of the 3,128 unsettled tempos (1,143 halved, 1,631 kept), moves
  3,867 uploads to the other octave in total, and makes 5,653 of them reliable, which the tag
  writeback then writes. `FOLD_VERSION` is 4, so the bpm-analyzer re-decides every measurement at
  start (issue #241).
<!-- release notes -->
- **Soundcloud and YouTube tempos use the uploader as a hint.** When a track's own genre, label or
  artist says nothing, the tempo of the other uploads in the same channel now decides between half
  and double tempo. Most tempos that were marked unsettled are now settled.
