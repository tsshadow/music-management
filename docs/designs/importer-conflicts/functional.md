# Standing Import Conflicts — Functional Design

## Overview
The importer's renamer and mover leave two folders in place when the name one of them wants is
already taken by a folder holding a *different* release. Nothing resolves such a pair until a person
looks at it, so the importer used to repeat the same WARNING for every pair on every five-minute
cycle: on 2026-09-25, 49 pairs produced about 490 WARNING events an hour, burying real warnings in
the event log and the alerts topic. Bug report
[091](../../bug-reports/091-importer-conflict-warning-spam.md).

A standing conflict is now warned about once, counted after that, and listed in Management so it can be
resolved. The importer still never deletes or merges either folder.

## User Stories
- As the curator, I get one warning when the importer meets a new folder conflict, not one every five
  minutes for as long as it stands.
- As the curator, I can see in Management which conflicts stand, since when, and which two folders they
  are, so I can compare them and remove or rename one.
- As the curator, once I have removed or renamed one of the two folders, the importer stops mentioning
  the pair without me telling it.

## Functional Flows
1. The renamer or mover finds that its target name is taken and the two folders hold different
   releases. The first time this pair is seen: one WARNING, the same text as before, and the pair is
   remembered.
2. Every later cycle, if neither folder changed on disk, the pair is not compared again and is only
   logged at DEBUG (which never reaches the event log).
3. If either folder changed (a file added, removed, rewritten), the pair is compared again. Still
   different: one INFO line. Now the same release: the source is parked in the quarantine as for any
   duplicate, and the pair is forgotten.
4. At the end of each cycle, a step that has standing conflicts, or just saw some resolved, logs one
   INFO line: `Standing folder conflicts (renamer): 49, 0 new this cycle, 0 resolved since the last one`.
5. A pair the step no longer meets — one of the folders was removed or renamed — is forgotten. If it
   ever comes back it is warned about again, once.
6. Management > Label proposals shows a read-only "Openstaande mapconflicten" section below the proposals:
   the folder that is already there, the folder waiting to move, the step, and since when.

7. Since bug report 119 the extract step files single files in the same list: a file in the import
   folder that is not an archive (a video, an image, a document, a loose track) or an archive that
   cannot be extracted. One WARNING the first time, the file is left exactly where it is, and it is
   not opened again until its size or modification time changes; once removed or renamed it drops
   off the list after the next cycle. The Management section is called "Openstaande importproblemen" and
   shows for each row what the problem is ("Geen muziek: videobestand", "Archief kon niet uitgepakt
   worden", "Naam al bezet door <map>").

## Acceptance Criteria
- A pair that stands for N cycles produces exactly one WARNING, also across an importer restart.
- Each cycle with standing conflicts produces one summary line per step, at INFO.
- A pair whose folder was removed is no longer reported and is gone from the Management list after the next
  cycle.
- No folder is deleted or merged because of a conflict; only an equal pair parks its source, as before.
- A non-archive file in the import folder is never extracted and produces one WARNING across any
  number of cycles; an archive that fails to extract produces one WARNING and stays in place; a
  normal archive still extracts and is quarantined as before.
- If the database is unreachable, the importer still warns once per pair within the running process,
  and warns once (not every cycle) that it cannot read its memory.

## Open Questions / Not Yet Decided
- Resolution is manual. A "keep this one" button in Management was left out on purpose: which copy is the
  right one needs listening, and deleting from an API request is a policy this project has not taken.
