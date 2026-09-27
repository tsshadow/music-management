- **A WAV file's date is read as text again** (issue #92, bug report 118). The ID3 date frames hold
  mutagen `ID3TimeStamp` objects, which the WAV reader passed on as they were: every WAV with a date
  logged "Could not split date value ['2023']" (270 warnings in two hours on production) and kept
  the date as an object.
<!-- release notes -->
- Fixed a flood of date warnings for WAV files.
