# Daily mix "Zachter" fails with a 500 on a Decimal tempo

# status: fixed

# reported problem

The "Zachter" daily mix (`/api/feeds/daily-mix-soft`) did not open on the web page; it looked
like the page asked for a feed that does not exist. Production's log showed a 500 instead:

```
TypeError: unsupported operand type(s) for -: 'decimal.Decimal' and 'float'
  services/music_manager/feeds/hardness.py, in tempo_hardness
```

# Possible reason

A track with no scored genre, no label mean and no artist mean gets its hardness from its tempo.
Since the measured BPM (`library_track_bpm`, 0.01 BPM, a DECIMAL column) became the tempo
source, pymysql returns it as `decimal.Decimal`, which cannot be subtracted from the float tempo
table. The soft mix reaches that fallback most often, so it failed first; any mix holding such a
track could.

# solution

`track_hardness` and `tempo_hardness` convert every database number to float before using it.
Test: `services/music_manager/tests/test_feeds_hardness.py::test_track_hardness_accepts_database_decimals`.
