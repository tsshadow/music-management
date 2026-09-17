# Frontend screenshots

`frontend:e2e` renders the web app twice on every merge request that touches it — as the desktop
shell at 1280×800 and as the phone shell at 412×915 — and compares one screenshot per route against
a committed reference. The references live in
`services/frontend/tests/browser/__screenshots__/<desktop|phone>/<route>.png` and are, at the same
time, the current pictures of the app: the browse grid on a phone is
`__screenshots__/phone/browse.png`.

The suite is `services/frontend/tests/browser/screenshots.spec.js`; the layouts are the two
projects in `services/frontend/playwright.config.js`.

## Reading a result

| Job colour | Meaning |
|---|---|
| green | every route still renders as its reference |
| orange (warning) | only screenshots differ — exit code 42, allowed by `.gitlab-ci.yml` |
| red | a functional browser test failed, or the stack never came up |

An orange job is not a pass. Open the job's artifacts: `services/frontend/test-results/` holds, per
differing route, `<route>-expected.png`, `<route>-actual.png` and `<route>-diff.png`. Either the
change is intended and the reference gets refreshed (below), or the layout broke and the branch
gets fixed.

The gate is soft on purpose while the suite is new. Once a few releases have gone by without a
false diff, remove the `allow_failure` block from `frontend:e2e` and a differing screenshot blocks
the merge like any other failing test.

## Refreshing the references

The screenshots are taken from the production build on the CI runner, and only there: a build on a
workstation renders with different fonts and a different Chromium, so a locally produced reference
would fail on the runner from day one. Refresh through CI:

1. Run the job with `MUMA_UPDATE_SNAPSHOTS=1` on your branch. From the shell:

       glab ci run -b <branch> --variables MUMA_UPDATE_SNAPSHOTS:1

   or start a pipeline from the GitLab UI with that variable set. The screenshot suite now rewrites
   the references instead of comparing.

2. Copy the rewritten set into the tree:

       ./scripts/test/frontend-screenshots-pull.sh <branch>

   This downloads the last `frontend:e2e` artifacts of that branch and copies
   `__screenshots__/` over the committed one. `git status` then lists what changed.

3. Look at the diff — an image diff in the GitLab MR view is the easiest — and commit. The next
   pipeline compares against the new set.

A route added to `ROUTES` in the spec has no reference yet: the first run writes one, reports the
test as failed (orange job), and the same pull script brings it in.

## What is and is not covered

Nineteen routes, viewport only, one of them (`/browse`) phone-only because the desktop renders
nothing there. Views that show live data — the management overview's version, the
health tab's uptime, the scanner's timestamps, events — are left out: they would go stale on every
release and say nothing about layout. Argument views (`/album/<id>`, `/artist/<name>`) need an id
the fixture set does not promise and are left out for the same reason. The stack holds a single
fixture track, so most lists render their empty or near-empty state; the layout is what is checked,
not the content.

The clock is pinned to 2026-06-15 12:00 Amsterdam time inside the browser so date-driven views (memories, the
greeting) render the same day every run. The browser locale is `nl-NL` and the
timezone Europe/Amsterdam. Animations are disabled and the text caret hidden; a difference of up to
0,5 % of the pixels is tolerated on top of Playwright's per-pixel colour threshold.

## When it flakes

- **Every screenshot differs slightly after a bump of `@playwright/test`.** A new Chromium
  renders text a hair differently. Renovate opens that bump as its own MR without automerge
  (`renovate.json`); refresh the references in that MR, that is the expected cost of the upgrade.
- **The runner changed.** The suite renders with the fonts and the Chromium of the LXC runner's
  host — the app uses system fonts, nothing is bundled. `frontend:e2e` is untagged for that
  reason and must stay on that one runner; a reference taken elsewhere fails from day one.
- **One route differs on a retry but not the next.** Something on that view is not settled when
  the picture is taken — a request the `networkidle` wait does not see, or a spinner without the
  `animate-spin` class. Fix the wait in the spec rather than raising the pixel tolerance.
- **The job went orange on `develop` without a frontend change.** The stack's data changed
  (a fixture, a seeded setting). Refresh, and note what moved in the MR.
