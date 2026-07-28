# Popular Genres Semicolon Delimiter

# status: fixed

# reported problem
`manager: statistics -> populair genres toont bv 'Euphoric Hardstyle;Hardstyle;Mainstream Hardstyle', maar in mijn huidige setup is een ; een delimiter, dus je moet er op splitsen`

# Possible reason
In `services/music_manager/routers/stats.py`, the `top_genres` query aggregates genres from `rules_genres` and `library_track_ml_labels` by grouping directly on the genre string column (`genre`). When database records contain compound genre strings separated by semicolons (e.g. `Euphoric Hardstyle;Hardstyle;Mainstream Hardstyle`), the grouping mechanism treats the entire compound string as a single distinct category instead of splitting the string by `;` and counting each individual subgenre.

# solution
Update the SQL query or post-processing logic in `services/music_manager/routers/stats.py` (and any related genre aggregation queries) to split comma- or semicolon-delimited genre strings into individual genre tokens, trim whitespace, and aggregate counts correctly per individual subgenre.
