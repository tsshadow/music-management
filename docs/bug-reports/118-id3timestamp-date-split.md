# WAV Dates Logged "Could not split date value" And Stayed Objects

# status: fixed

# reported problem
GitLab issue #92. Production event log, 2026-09-26 12:23 to 14:18: 270 `WARNING` rows from the
music-manager process, logger `root`, reading
`Could not split date value ['2023']: 'ID3TimeStamp' object has no attribute 'split'`, during a
full scan.

# Possible reason
`Tag.__init__` splits every value of a list on `;`, and logs this warning when that fails.
`TagCollection._parse_wav` handed the ID3 frame's `.text` to `Tag` unchanged. For text frames
that is a list of `str`, but the time frames -- `TDRC` (date) and `TDOR` (original date) -- hold
mutagen `ID3TimeStamp` objects, which have no `split`. MP3 files are not affected: they are read
through EasyID3, which already returns the date as text. So every WAV with a date logged the
warning on every read, and its date tag held an `ID3TimeStamp` instead of a string.

# solution
`_parse_wav` converts each frame value to text (`_id3_frame_text`); `str()` of an `ID3TimeStamp`
is its text, so nothing is lost and the WAV read now matches the MP3 one. Test with a real mutagen
`TDRC`/`TDOR` frame in `services/tagger/Song/TagCollectionTest.py`.
