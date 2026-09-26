- **Livesets, sets & mixes and podcasts apart in the car, by voice and in presets** (issue #47).
  The Sets tab in Android Auto gets a **Soort** row -- Sets & mixes, Livesets, Podcasts -- each a
  folder with play all, shuffle, recently added and per year. Voice understands "livesets" / "live
  sets", "dj sets" and "podcasts" ("speel livesets van Defqon 2019 af"); a bare "set" still means
  every long track. A sets preset saved with a Soort plays that Soort in the car. With a Soort and
  one year, the year is the year a liveset was *played* (its performance date), as on the web;
  without a Soort the year keeps its old meaning. Only the four forms the server knows are ever
  sent -- an unknown one would fail the whole request -- so an unrecognised value simply filters
  nothing.
<!-- release notes -->
- Android Auto and voice can ask for livesets, sets & mixes or podcasts, and a liveset is found under the year it was played.
