- **A setting changed on one device no longer disappears when another device saves at the same
  moment** (issue #39, bug report 116). The account's settings blob could only be written whole, so
  the web player and the app each read it, changed their key and posted everything back -- and the
  second of two near-simultaneous saves wiped the first one's change. New
  `PATCH /api/users/{id}/settings/{app_id}` with `{"set": {...}, "remove": [...]}` changes only the
  named top-level keys, as a `SELECT ... FOR UPDATE` read-merge-write in one transaction, and
  answers the merged blob. The web player now sends only the keys it changed, without reading
  first. Additive: `POST` still replaces the whole blob for older app versions, and a new client
  falls back to it when a server answers the PATCH with 405. The music server's MuMa proxy now
  forwards PATCH too; before, it sent nothing and held the call for 30 s, and it now answers any
  verb it does not forward with an immediate 405.
<!-- release notes -->
- Settings changed on your phone and in the web player at the same time no longer overwrite each
  other.
