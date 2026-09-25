# SoundCloud Coverage Never Finds the Last Download

# status: fixed

# reported problem
Found while building channel links (docs/designs/channel-links/), 2026-09-25. On the Volledigheid tab
(Beheer -> Downloaders), every SoundCloud account showed "onbekend" as its last download, including
accounts that downloaded that same day. YouTube accounts showed dates normally.

# Possible reason
`CoverageQueries.last_downloads` grouped `downloads_soundcloud_archive` by `account` and
`build_coverage` looked each configured account up by its name (the slug, e.g. `brainimpact`). The
SoundCloud downloader, however, files every archive row under the account's numeric `soundcloud_id`:
on production 157.887 of 157.888 rows have a numeric `account`, and 1.099 of the 1.113 configured
accounts are found in the archive by `soundcloud_id`. Name and id never match, so the lookup always
missed. The YouTube archive does key on the channel name, which is why only SoundCloud was affected.
The unit tests fed the endpoint canned data keyed by name, so they agreed with the bug.

# solution
`CoverageQueries.configured` also reads `soundcloud_id` and stores it as the account's
`archive_key`; `build_coverage` looks the last download (and, new with channel links, the archive
path that leads to the channel) up by `ConfiguredAccount.archive` — the archive key when there is
one, the schedule key otherwise. Tests: `test_a_soundcloud_account_is_found_in_the_archive_by_its_numeric_id`
in `services/music_manager/tests/test_downloaders.py`, the archive-key case in
`test_downloader_coverage.py`, and `ChannelLinksTest.test_the_coverage_page_shows_the_link_through_the_archive`
in `tests/integration/test_router_sql.py`, which inserts a numeric archive row against real MariaDB.
