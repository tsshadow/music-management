# Genre Hierarchy Accepts Cycles

# status: fixed

# reported problem
Audit item C12 (2026-09-23, from reading the code). `PUT /api/curation/genres/{name}/parents`, the
write behind the "Valt onder" field on the genre edit page, checked that a genre was not its own
parent but nothing more. Filing Hardcore under Uptempo while Uptempo already sat under Hardcore was
stored without complaint, and so was any longer loop (Hardcore -> Upterror -> Uptempo -> Hardcore).

Everything that walks `rules_subgenre_hierarchy` then misbehaved:

- `feeds/hierarchy.py` `deepest()` counted every member of a cycle as an ancestor of the others and
  dropped all of them, so a track tagged with both genres contributed to neither in the taste
  profile, the genre buckets or the daily mixes.
- `ancestors()` reported a genre as its own ancestor, and `nearest_ancestor()` could hand a genre
  its own hardness to "inherit".
- Nothing reported the cycle anywhere, so the only symptom was a feed that quietly under-counted.

The walkers already had a depth bound, so nothing hung; the damage was silent data loss, not a
stall.

# Possible reason
The endpoint validated each proposed parent on its own (exists, accepted by curation, not the genre
itself) and never looked at the graph the new edge joins. The module docstring of `hierarchy.py`
already anticipated "a hand-entered row can close a cycle" and guarded against hanging, but not
against the walkers' answers being wrong once one existed.

# solution
- The `PUT` reads the whole hierarchy once and walks up from each proposed parent (bounded at 64
  levels plus a seen set, so a cycle already in the table cannot hang the request). If the edited
  genre is reached, it answers `409` with `"<genre> is already an ancestor of <parent>"` and writes
  nothing. The check runs before `transaction(conn)` opens (bug report 062), so a
  refused request never starts a transaction; the replace itself stays one transaction. Self-parenting stays the
  existing `400`.
- `hierarchy.py`: `ancestors()` and `nearest_ancestor()` never return the genre itself. `deepest()`
  treats genres that sit in a cycle together as one and keeps the alphabetically first, so a tag is
  never lost and the choice is the same on every call; a genre strictly below the cycle still wins as
  before. New `find_cycles()` (iterative Tarjan) and `warn_cycles()`, which the two loaders (feeds
  build and hardness inheritance) call once per load: one `WARNING` naming the cycle members, never
  one per `deepest()` call.
- `GET /api/curation/genre-hierarchy/cycles` reports every stored cycle, read-only. No migration:
  SQL cannot tell which edge of a loop is the wrong one, so that is a curator's decision.
- `GET /api/curation/genres/{name}` also returns `descendants`, and the edit page refuses a
  descendant as a parent before calling the backend. A 409 that still gets through (another tab)
  is shown in the page's existing error banner, which renders the backend `detail` as-is.

**Operator action after deploy:** call `GET /api/curation/genre-hierarchy/cycles`. For each cycle it
lists, open one of its genres in Beheer (genre edit page) and remove the parent that points back
into the loop. Until then the feeds keep working with the deterministic choice above and log one
`WARNING` per load.
