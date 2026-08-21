# Dynamic Playlists Come Back Nearly Empty

# status: fixed

# reported problem
A seeded dynamic playlist such as "Hardstyle", configured for 500 tracks, returns a handful of rows
instead. It reads as "the library simply has little hardstyle", which is why it sat unnoticed:
production holds exactly two dynamic playlists, the feature works, returns almost nothing, and so
nobody uses it. Found while researching daily mixes on 2026-08-17.

# Possible reason
`routers/users.py` built the track query with `rating_tracks` joined in by LEFT JOIN:

```sql
LEFT JOIN rating_tracks rt ON rt.entity_id = t.track_uid AND rt.username = %s
```

and then always appended the rating filter:

```python
if rating_range:
    query += ' AND (rt.rating >= %s AND rt.rating <= %s)'
```

`rating_range` defaults to `[0, 100]`, which the UI means as "the whole scale, so no filter". But an
unrated track's `rt.rating` is NULL after a LEFT JOIN, and NULL fails both comparisons — SQL's
three-valued logic makes the whole predicate NULL, which is not true, so the row is dropped.

The library holds 1.221 ratings against 302.561 tracks. The default rating range therefore excluded
301.340 tracks, or 99,6% of the library, from every dynamic playlist. Narrowing the genre on top of
that is what left a handful of rows.

The same shape does not appear anywhere else in the service: `rt.rating >= %s` occurs once.

# solution
A range that covers the whole scale now builds no clause at all, so the LEFT JOIN's NULLs are never
compared:

```python
if rating_range and not (rating_range[0] <= 0 and rating_range[1] >= 100):
```

A narrower range is a deliberate rating filter and keeps excluding unrated tracks, which is what
asking for "4 stars and up" means. Only a full range is read as no filter, so a bound the user
actually chose is never quietly widened.

No migration is needed: the seeded defaults store `rating_range: [0, 100]`, which is now correctly a
no-op rather than a filter that hides the library.

Covered by `DynamicPlaylistTracksTest` in `services/music_manager/tests/test_users_endpoints.py`:
the full range and a missing range build no clause, a real lower or upper bound still filters, and a
range wider than the scale is still no filter.
