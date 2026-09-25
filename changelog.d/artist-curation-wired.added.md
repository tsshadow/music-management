- **A name a tagger rule guessed no longer confirms itself on the next file.** The tagger matched
  titles against every name in `library_artists`, and the scanner records every artist it reads, so a
  guess was a trusted artist one scan later -- the loop that once put 9.188 tracks under `Premiere`.
  The artist rules now trust only approved names (by hand or by the external-evidence run) and the
  names that were already in the library before this release (`rules_artist_legacy_trust`, seeded
  once by `migrate_v40`). A new name is recorded, stays on the file it came from, and is listed in
  Artiestcuratie with a **Nieuw** badge (`state=pending`, `pending` in the summary) until it is
  decided. Measured on production: ~3.500 new names in 30 days, 20-35 on a quiet day, over a thousand
  after a mass retag.
- **A rejected artist is now also removed or corrected by CheckArtistRule.** It asked the artist list
  before the ignore list, and every rejected name that was ever on a file was in that list, so the
  rejection was skipped: 996 rejected names are still on 29.772 tracks. They change the next time
  each file is tagged.
<!-- release notes -->
- The tagger only recognises approved artist names; new names wait in Artiestcuratie as "Nieuw" instead
  of being trusted on sight.
- Rejected artists are now actually removed from files on their next tag pass.
