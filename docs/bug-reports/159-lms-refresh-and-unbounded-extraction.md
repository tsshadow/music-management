# LMS Track Refresh Skips The Permission, Extraction Has No Size Limit

# status: fixed

# reported problem
A second review of develop (`4446afe83`, 2026-11-09) after bug report 158 found two gaps that report left open.

1. LMS answers `/muma/api/tracks/{id}/refresh` itself and calls MuMa's `rerun-parse-path` with the MuMa system key, for any caller it authenticated. That route needs `rules.manage` since issue #216, so a listener could still start a retag through LMS (issue #230).
2. The extractor checked an extraction for links out of its folder only after the backend finished. Nothing limited how much the backend wrote, so a small, highly compressed archive could fill the import filesystem first (issue #231).

# Possible reason
1. LMS knows a caller's admin role and no other MuMa permission, and the refresh branch was written before MuMa gated the route. It sent the system key so that a Subsonic caller, who has no MuMa key, could reach MuMa at all.
2. patool runs the backend as a child process and waits for it. An archive's own header says nothing reliable about how much it expands to, so a check before or after the run does not hold.

# solution
1. `trackRefreshKey` in `services/music-management-server/src/libs/muma/Authentication.cpp` decides the key. A MuMa user key goes through as itself, so MuMa checks `rules.manage` for that user. A system caller gets the system key. A `u`/`p` or token caller gets it only as an LMS admin. Anyone else gets `403`, and LMS sends nothing to MuMa. The web player shows the reload button to admins only. GTest cases in `test/Authentication.cpp` cover each caller kind.
2. `services/importer/extract_budget.py` measures the staging folder every 0.5 s while the backend runs. It kills the processes the extraction started when the folder passes `import_extract_max_gb` (default 50) or the free space drops below `import_extract_min_free_gb` (default 10). The archive stays with reason `extraction-too-large`, and no other backend is tried. A test runs a real writer process against a 64 KiB budget and checks that it is killed, that a child started earlier survives, and that the other files in the import folder stay.
