- **The artist evidence run now runs by itself, once a day, inside music-manager** (issue #49,
  `docs/designs/artist-curation/technical.md`, "Scheduled evidence run"). `tools/artist_auto_approve.py`
  approved 5.903 names when it was run by hand on 2026-09-20; since then only 8 of ~3.300 new names
  left the queue. The new `artist-auto-approve` loop looks up every new (pending) name plus 300
  older ones a day, most tracks first, on Deezer, iTunes and MusicBrainz at their documented rates,
  with the tool's own rules (the judgement moved to `services/common/Helpers/ArtistEvidence.py`, so
  both share it). A round is bounded (1.000 names, 180 minutes), writes one INFO line to the event
  log and a row to the new `rules_artist_evidence_runs`; verdicts live in `rules_artist_evidence`
  (migrate_v47). **Dry run is on by default**: it approves nothing until "Artist curation -> dry run"
  is switched off in Beheer, after which the first round also applies what the dry runs judged
  approvable. Approvals are signed `auto-external`, never overwrite a curator's decision, and an
  undone approval is never made again; nothing is ever rejected automatically. Review them on the
  Goedgekeurd tab with the new "Automatisch (bewijsronde)" filter (`GET /api/rules/artists` gains
  `decided_by` and `sort=decided`), or per round via `GET /api/rules/artists/auto-approve/runs`.
  Measured on prod: 49.382 undecided names, 325 of them new; about 20-25 minutes of lookups a day.
<!-- release notes -->
- The artist curation queue is now checked against Deezer, iTunes and MusicBrainz every night.
  It starts in dry run: switch it on in Beheer -> Config -> Artist curation once a round looks
  right, and review what it approved under Goedgekeurd -> Automatisch.
