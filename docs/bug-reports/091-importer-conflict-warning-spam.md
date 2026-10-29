# The Importer Warns About The Same Folder Conflicts Every Cycle

# status: fixed

# reported problem
On production the importer logs
`Conflict: <target> already exists but its contents differ from <source>. Leaving both in place for manual intervention`
at WARNING for the same folder pairs on every cycle (`services/importer/renamer.py`,
`services/importer/mover.py`). Every WARNING is a row in the `events` table and a candidate for the
alerts topic (deduplicated per five minutes), so this noise inflates the event log and hides real
warnings.

Measured read-only on production, 2026-09-25, `events` bounded by `created_at` and `level = 'WARNING'`:

| window (UTC) | conflict WARNINGs | distinct messages |
|---|---|---|
| 17:00–18:00 | 490 | 49 |
| 18:00–19:00 | 441 | 49 |
| 19:00–19:30 | 245 | 49 |
| 19:53–20:05 (after the 0.75.0 deploy) | 147 | 49 |

So **49 distinct pairs stand**, each warned about ~10 times an hour (one per five-minute cycle). All 49
come from the **renamer**: every target is in the import folder (`/mnt/music/EPs/__TODO/`), none from
the mover (0 mover conflicts in the 24 hours before 20:05). 18 of the 49 targets carry the empty
catalogue-number prefix ` - ` of bug report 087; 31 carry a real one (`HCL116 - …`, `GH-124 - …`).
None of the 1.323 were the "holds the same files" variant.

# Possible reason
Every one of the 49 has the same shape: the source is an unparsed folder (`X`) and the target is that
same name after the renamer's prefix (`<CAT> - X`, or ` - X`). So a release folder was renamed once
and then a *second* folder with the identical name arrived in the import folder — the same archive
extracted twice. Both copies have `rules_label_proposals` rows created on 2026-08-20 (e.g.
`HCL116 - Double_Phunq_-_Wizard…` at 06:51 and `Double_Phunq_-_Wizard…` at 09:06), so they have been
sitting side by side since then; they became visible as WARNINGs when the ENOTEMPTY handling in
`Renamer.run` started routing the collision to `_resolve_collision` instead of a generic INFO line.

`is_same_release` says they differ — the track list or a track length does not match. The most likely
cause is that one of the two extractions was incomplete: extracting straight into the import folder
(before the staging change of 2026-09-23) let a later cycle see a half-written release. This was not
verified on disk: the investigation stayed on the read-only database account.

Why it repeats: neither step remembered a conflict. Nothing on the next cycle is any different, so the
same pair was compared again — reading the length of every track over CIFS — and warned about again.

# solution
`services/importer/conflict_store.py` (design: `docs/designs/importer-conflicts/`):

- The renamer and mover remember each unresolved pair in a new table `importer_conflicts`
  (`migrate_v43_importer_conflicts.sql`), with a fingerprint of both folders (entries, size, newest
  mtime — `folder_signature`, no file opened).
- The WARNING is logged only the first time a pair is seen. After that an unchanged pair is not even
  compared again (DEBUG only); a pair where a folder changed is compared again and, still different,
  logged at INFO; one that became equal is parked in the quarantine as any duplicate.
- Each cycle ends with one INFO line per step with standing conflicts:
  `Standing folder conflicts (renamer): 49, 0 new this cycle, 0 resolved since the last one`.
- A pair no longer met (a person removed or renamed one of the folders) is forgotten.
- Without the database the importer remembers pairs in-process, and warns once — not every cycle —
  that it cannot read the table.
- `GET /api/import-conflicts` and a read-only section under Beheer → Labelvoorstellen list what stands,
  so a person can resolve it. Nothing deletes or merges a folder.

Expected effect on production: 49 WARNINGs once after the deploy (the table starts empty), then ~10
INFO summary lines an hour instead of ~490 WARNINGs. The 49 pairs themselves still need a person;
see the GitLab issues.
