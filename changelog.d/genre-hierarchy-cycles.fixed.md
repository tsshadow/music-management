- **A genre could be filed under its own subgenre, and the daily mixes then lost both.**
  `PUT /api/curation/genres/{name}/parents` only refused a genre as its own parent, so Hardcore
  under Uptempo under Hardcore was stored, and `deepest()` in the feeds dropped every genre in the
  loop. The write now answers `409` ("Hardcore is already an ancestor of Uptempo"), the edit page
  refuses a subgenre as a parent up front, the feed walkers keep one genre of a stored cycle (the
  alphabetically first) and log the cycle once per load, and
  `GET /api/curation/genre-hierarchy/cycles` lists any cycle already in the table so it can be
  fixed in Beheer (bug report 064).

<!-- release notes -->

- **Genre hierarchy:** a genre can no longer be placed under one of its own subgenres; existing
  loops are reported and no longer make the daily mixes skip those genres.
