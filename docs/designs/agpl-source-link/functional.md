# AGPL source link — Functional Design

## Overview

AGPL-3.0 section 13 requires that people who use the server over a network can get its source code.
The About screen shows a Source code section with a link to the place where the source is published.
The administrator sets that address. The app shows the same screen, so one change covers the web player
and the Android app.

## User Stories

- As a listener, I want to find the source code of the server I use from the About screen, so that I can
  read or copy it as the license promises.
- As an administrator, I want to set where the source is published, so that a fork points at its own
  repository.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A listener opens Settings > About | A Source code section shows the address as a link. |
| The listener taps the link in a browser | The address opens in a new tab. |
| The listener taps the link in the app | The address opens in the system browser. |
| A person opens the login screen | A small Source code link is under the form. |
| The administrator clears the setting | The section is not shown. |
| The setting holds a non-web address such as `javascript:` | The section is not shown. |
| MuMa cannot be reached | The section is not shown, like the MuMa version. |

## Acceptance Criteria

1. About shows the section and link when `public_source_url` is an http(s) address.
2. The default is `https://github.com/OWNER/music-management`, a placeholder to replace.
3. Changing the setting on Management > Configuration changes the link without a deploy.
4. An empty or non-http(s) value hides the section.

## Open Questions / Not Yet Decided

- The placeholder becomes the real repository address when the repository is published (#189).
- The legacy LMS Wt About window is not changed, see the technical design.
