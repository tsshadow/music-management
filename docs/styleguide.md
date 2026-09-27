# 🎨 Music Management System Style Guide

## Theme & Brand
- **Theme**: Spotify Dark (immersive dark mode optimized for music streaming, long-term listening, and management).
- **Brand Personality**: Sleek, modern, efficient, music-centric, professional yet accessible.
- **Tone and Voice**: Clear, concise, modern, helpful, direct.
- **Design Principles**:
  - Immersive dark aesthetic that highlights cover art and media.
  - Consistent layout paradigms across Web UI (`services/frontend`) and Android mobile (`services/muma-mobile`).
  - Generous whitespace and clean information hierarchy.

## Colors
- **Primary Accent**: `#1DB954` (Spotify Green) — Primary actions, active states, highlights, playback indicators.
- **Brand token (Web)**: the accent follows the listening mode — `#1DB954` in songs mode, `#2D5AFC`
  (blue) in sets mode. In `services/frontend` write it as the Tailwind token (`bg-brand`,
  `text-brand`, `border-brand`, `accent-brand`, `focus:border-brand`), never as `#1DB954`, so
  `:root.mode-sets` in `src/app.css` can switch it. **Never declare a `:global(...-brand)` rule in a
  component**: Tailwind's utilities live in `@layer utilities` and any unlayered rule beats them,
  so one such rule turns the whole app green in sets mode (bug report 041;
  `tests/unit/brandToken.test.js` fails on it). The login page is the one deliberate exception: it
  is shown before any mode applies and stays `#1DB954`.
- **Background (Main)**: `#121212` (Dark Charcoal) — Default content view background.
- **Background (Sidebar / Navigation)**: `#000000` (Pure Black) — Sidebar, bottom navigation bars.
- **Surface (Cards / Modals / Rows)**: `#282828` (Medium Gray) — Cards, hover overlays, input backgrounds, active tabs.
- **Semantic Colors**:
  - Success: `#1DB954` (Spotify Green)
  - Warning: `#FFA726` (Amber)
  - Error: `#E53935` (Red)
  - Info: `#29B6F6` (Light Blue / Neutral Accent)
- **Text Colors**:
  - Primary (Headings, titles): `#FFFFFF` (White)
  - Secondary (Subtitles, metadata, inactive items): `#B3B3B3` (Light Gray)
  - Muted (Timestamps, disabled): `#727272` (Dark Gray)

## Typography
- **Font Families**: Sans-serif system font stack (Inter, Roboto, SF Pro, Helvetica Neue).
- **Font Sizes**:
  - Display / Title: 24px - 32px (Web), 20px - 26px (Mobile)
  - Section Headings: 18px - 20px (Web), 16px - 18px (Mobile)
  - Body Text: 14px - 16px (Web), 14px (Mobile)
  - Captions / Metadata: 12px (Web & Mobile)
- **Font Weights**: Regular (400), Medium (500), Bold (700).
- **Line Heights**: 1.2 for headings, 1.5 for body text.

## Spacing & Layout (Web vs Mobile)
- **Spacing Scale**: Base unit 4px (Tailwind scale: `p-1` = 4px, `p-2` = 8px, `p-4` = 16px, `p-6` = 24px).
- **Mobile vs Desktop Considerations**:
  - **Web UI (Desktop / Tablet)**:
    - Fixed or collapsible sidebar (`w-64`), fluid main content container with padding (`p-6` to `p-8`).
    - Multi-column grid layouts for albums, artists, and playlists (`grid-cols-2 md:grid-cols-3 lg:grid-cols-5`).
  - **Android UI (MuMa Mobile / Mobile)**:
    - Compact touch targets (minimum 48x48dp).
    - Bottom navigation bar or hamburger menu for navigation.
    - Single-column lists or compact 2-column grids for track and album browsing due to limited screen width.
- **Margins & Padding**: Generous spacing around major UI blocks to prevent clutter.

## Components
- **Buttons**:
  - Primary: Rounded full (`rounded-full`), brand background (`bg-brand` on the web; green in songs mode, see "Brand token" above), dark text or white bold text.
  - Secondary: Transparent with border or surface gray background (`bg-muma-spotify-light`), white text.
- **Forms & Inputs**: Dark background (`bg-muma-spotify-light`), subtle border, brand focus ring (`focus:border-brand` on the web, see "Brand token" above), white text.
- **Cards**: Surface gray (`bg-muma-spotify-light`), rounded corners (`rounded-md` or `rounded-lg`), smooth hover elevation/scaling.
- **Modals**: Centered overlay with backdrop blur or dark translucent background (`bg-black/80`), rounded card container.
- **Confirmation dialog**: a question that needs a yes before something hard to undo happens is
  `Modal.svelte`, never the browser's `confirm()` for anything a listener (not only an admin) sees.
  The title is the question ("Log out?"), the body says in `text-sm` what happens and what does not,
  and the buttons sit right-aligned: an outlined pill `common.cancel` (`bg-transparent border
  border-muma-spotify-muted text-white px-6 py-2 rounded-[24px] font-bold`, hover `border-white`)
  followed by a brand pill naming the action (`bg-brand text-black px-6 py-2 rounded-[24px]
  font-bold`). A short question passes `widthClass="max-w-md"`. Escape, the close button and the
  backdrop all mean cancel. Examples: the set-size download question (`TrackList.svelte`) and the
  logout confirmation (`ProfileButton.svelte`, `docs/designs/logout-confirmation/`). A dialog opened
  from inside a `backdrop-blur` bar is moved to `<body>` with `use:portal` (`src/lib/portal.js`),
  or the bar clips it.
- **Navigation**: Persistent sidebar on Web, Bottom Navigation / Drawer on Android. Active items highlighted with white text and/or green accent.
- **Load more**: a list that continues past what it shows ends in one centred, outlined pill under
  the list (`bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px]
  font-bold`, hover `border-white` and `scale-[1.04]`), labelled `common.loadMore` ("Meer laden")
  and `common.loading` while the next page is on its way. It disappears when there is nothing more;
  it never shows a count or a page number. Used by the song, artist and album lists and, since
  2026-09-26, the feed pages (`FeedView.svelte`, `docs/designs/feed-length/`). A queue started from
  a feed tops itself up near its end, and since 2026-09-27 the queue list (the bottom sheet on the
  phone and the tablet, the side panel on the desktop) also ends in the same pill while its feed has
  a next page (`QueueFeedLoadMore.svelte`, bug report 122). The Now Playing screen itself gets no
  button. Rows a list could not show, such as feed paths the server has no song for, are
  mentioned once in the list's header meta line in the muted text colour ("• 2 niet gevonden op de
  server"). The row count stays the count of what can be played.
- **Sign in with Google**: in a browser the login page renders Google's own button (Google
  Identity Services, `theme: "outline"`, pill shape). Inside the Android shell Google's web
  sign-in cannot run, so `LoginPage.svelte` draws the same button itself and the shell signs in
  natively: full-width `rounded-full` pill, white background, `#1f1f1f` text in `text-sm
  font-medium`, 1px `#747775` border, Google's four-colour "G" at 18px left of the label, below the
  hairline-flanked "OF" divider that separates it from the password form. It is only shown when the
  app was built with a Google client ID; there is never a button that can only fail.
- **Session controls**: "Log out" lives in the overflow/secondary menu (Android: the toolbar
  overflow, directly above "Exit"), never as a primary action. It always confirms first, stating
  what is lost (playback stops) and what is kept (downloads), and it returns the user to the login
  screen rather than to an empty app. On the web and in the app (the same web UI) that
  confirmation is a Confirmation dialog, see below; the line about downloads only shows in the app,
  since a browser tab has none (issue #80).
- **Curation state badges** (Beheer -> Curatie tables): a small uppercase label
  (`text-[10px] font-bold uppercase px-2 py-0.5 rounded`) under the name. Approved is brand
  (`bg-brand/20 text-brand`), rejected is red (`bg-red-500/10 text-red-500`), and *pending* --
  a name the tagger does not trust yet (artist curation, "Nieuw") -- is yellow
  (`bg-yellow-500/10 text-yellow-500`), the colour the queue's own "to review" icon already uses.
  A badge states a fact about the row; it is never the only way to act on it.
- **Memory card**: represents one release *year*, never a single track. Its title is the relative
  age ("Today, 8 years ago"), its secondary line is the year and the track count, and its artwork is
  the cover art of the first track in that year's group. It uses the standard card surface and
  radius above; nothing about it is visually special, which is the point — a memory is a normal card
  with a time-based title.
- **Memories wording**: a group heading says "Today" only when the group contains a release that
  falls on today's exact date. A group that exists only because of the surrounding-days window says
  "This week" instead. The heading never claims a precision the tags do not have.
- **Memories placement**: on the home screens (web and Android) memories are one horizontally
  scrolling carousel above the existing rows, capped at ten cards, and hideable from settings. The
  full Memories screen shows one section per year, newest year first, each section holding that
  year's tracks and its own play action. The carousel is a teaser; the permanent way in is the web
  sidebar entry and the Android Library tab, neither of which the setting affects.

## Loading States (Skeletons)
- **Rule**: A screen that fetches remote content never shows an empty page while waiting. It shows
  skeleton placeholders in the shape of the content that is coming.
- **Placeholder color**: `#2F2F2F` (one step lighter than the `#282828` card surface, so a skeleton
  reads as "content is coming", not as an empty card). Android token: `@color/skeleton_block`,
  drawn via `@drawable/skeleton_block` (4px corner radius, matching the small-radius rule below).
- **Shape**: placeholders mirror the real component's dimensions and position, so content does not
  shift when it arrives (Android: `home_skeleton_carousel`/`home_skeleton_grid` mirror
  `home_card_carousel`/`home_card_grid`).
- **Motion**: a slow alpha pulse (1.0 → 0.4, 700ms, reversing) — `@anim/skeleton_pulse` on Android.
  No sweeping shimmer gradients, and no third-party shimmer dependency.
- **Granularity**: each section owns its own loading state and replaces its own skeleton as soon as
  its data arrives; one slow section never holds up the ones that are ready.
- **Refresh**: re-loading a screen that already shows content keeps that content on screen —
  skeletons are for the first load, not for every refresh.

## Borders & Effects
- **Border Radius**: Small (`rounded` / 4px) for inputs/buttons, Medium (`rounded-md` / 8px) for cards/modals, Full (`rounded-full`) for avatars and primary action pills.
- **Shadows**: Subtle soft shadows (`shadow-lg`, `shadow-black/50`) to lift floating elements and modals.
- **Opacity Rules**: Disabled elements at `opacity-50`, hover states transition smoothly.

## Animation & Accessibility
- **Transitions**: Fast duration (150ms - 250ms), ease-in-out (`transition-colors`, `transition-transform`).
- **Accessibility**: High contrast between text (`#FFFFFF` / `#B3B3B3`) and background (`#121212`), clear focus states, touch targets at least 48x48px on mobile.

## Coding Conventions
- **Web (`services/frontend`)**: Svelte components + Tailwind CSS utility classes using the color tokens
  declared in the `@theme` block of `src/app.css`. A token that is not declared there compiles to no CSS
  rule at all, silently -- add it to `@theme` first, then use it. Write the token, never the hex it stands
  for (`text-muma-spotify-text`, not `text-[#b3b3b3]`); an arbitrary `-[#hex]` value is only for a colour
  that has no token yet.

  | Token | Hex | Use |
  |---|---|---|
  | `brand` | mode: `#1DB954` / `#2D5AFC` | the accent (active states, primary buttons) |
  | `brand-green` / `brand-blue` | `#1DB954` / `#2D5AFC` | a fixed accent that must not follow the mode (login page) |
  | `muma-spotify-black` | `#191414` | page ground |
  | `muma-spotify-dark` | `#121212` | main content background |
  | `muma-spotify-panel` | `#181818` | panels, sidebars, filter bar |
  | `muma-spotify-raised` | `#242424` | a surface one step above the panel (inline editors, nested cards) |
  | `muma-spotify-light` | `#282828` | cards, rows, inputs, neutral chips |
  | `muma-spotify-hover` | `#333333` | hover / pressed state of a `light` surface |
  | `muma-spotify-highlight` | `#3E3E3E` | hover of a control that already sits on `hover` |
  | `muma-spotify-text` | `#B3B3B3` | secondary text (subtitles, metadata, inactive items) |
  | `muma-spotify-muted` | `#727272` | muted text (timestamps, disabled) |
  | `muma-spotify-subtle` | `#535353` | dimmest text: placeholder glyphs, empty states |

  Opacity uses the Tailwind v4 modifier on the colour (`hover:bg-muma-spotify-light/80`); the v3
  `bg-opacity-*` / `text-opacity-*` utilities compile to nothing in v4.

  Colours still written as arbitrary values, because no token covers them yet: `#1a1a1a` (settings and
  management sidebars), `#2a2a2a` (login inputs, search field), `#444` (device settings hover), `#4d4d4d`,
  `#4e4e4e`, `#555`, `#777`, `#8a8a8a`, `#d0d0d0`, `#e5e5e5`, `#1ed760` (login button hover), `#e91429`,
  `#eb743b`, `#b266ff` (radio/news active) and the label-chip ambers `#3a2c16`, `#4a3820`, `#ffcc80`,
  `#ffe0b2`, and Google's own button colours `#1f1f1f` (text) and `#747775` (outline) on the native
  "Sign in with Google" button below -- Google's branding rules fix those, so they never become MuMa
  tokens. Promote one to a token (with a name for its role) when a second place needs it.
- **Web text**: every user-visible string comes from `src/lib/i18n/locales/*.json` through `$t`, and
  numbers and dates are formatted with the active locale (`$format.number`, `$format.date`,
  `$format.dateTime` from `src/lib/i18n/index.js`), never a fixed `'nl-NL'`.
  `tests/unit/noHardcodedDutch.test.js` fails on the phrases that were moved and on `nl-NL`.
- **Android (`services/muma-mobile`)**: Kotlin + Material Design components customized with dark theme color attributes matching the web palette.

## Do's & Don'ts
- **Do**:
  - Maintain consistent dark mode aesthetics across web and mobile.
  - Use generous whitespace and clean typography hierarchy.
  - Reuse established components and color tokens.
- **Don't**:
  - Don't introduce unauthorized color palettes (e.g., standard bright blue links).
  - Don't mix incompatible UI frameworks or design languages.
  - Don't use cramped touch targets on mobile devices.

## Style Update Workflow & Todo Backlog
To maintain clean design governance and prevent ad-hoc style drift:
1. **Proposal & Approval**: Any new style, component variation, or design token must be proposed and receive dev approval.
2. **Style Guide & Todo Tracking**: Upon approval, new or pending styles must first be registered in this style guide (under a pending todo section or design backlog) before code implementation begins. This acts as a design contract and checklist.
3. **Code Implementation**: Once documented, implement the approved styles in code (`services/frontend` or `services/muma-mobile`), then mark the item as completed in the style guide.

### Design Backlog

- **Done** — Feed length (2026-09-26, `docs/designs/feed-length/`): no new token or component. The
  existing load-more pill is documented above under Components ("Load more") and reused as-is under
  a feed's track list.
- **Done** — Feed "Meer laden" in the queue (2026-09-27, bug report 122): no new token. The same
  load-more pill under the queue list for a feed queue, and a muted "not found on the server" note
  in the feed header meta line, both documented above under Components ("Load more").
- **Done** — Versies page in Beheer (2026-09-26, `docs/designs/song-versions/`): built only from
  existing tokens. The list is the curation table surface (`bg-muma-spotify-panel/40`, rows
  `divide-muma-spotify-panel/30`); a row expands in place to the versions table instead of opening
  a page. Badges follow "Curation state badges": *Best* and *Pinned* are brand, *Changed* and
  *Was best* are yellow (a rescore result to review). Primary action ("Accept new choice") is the
  brand pill; "Pick as best" and "Reset to automatic" are secondary pills (`bg-muma-spotify-light`).
- **Pending** — Phone UI polish (2026-09-17, `docs/designs/phone-ui-polish/`), one item per increment:
  - A (done): artwork fallback chain cover → artist image → tinted title panel (`Artwork.svelte`); the
    full-screen player background is a vertical gradient from the track's genre tint (55% mix with
    `#121212`) to `#121212` at 60%; the mini player shows one square image.
  - B (done): player header is two lines (caption `11px #B3B3B3`, name `14px bold white`, sentence case);
    genres and label are chips (the details-sheet chip); stars are 44px targets with a 24px glyph
    (28px since J);
    transport and bottom-row icons at 24px, shuffle/repeat included.
  - C (done): Home "show all" in sentence case at 13px; odd tile counts span the last tile; recent-track
    shelves are compact rows (48px thumbnail); Browse tiles 68px high with a 36px icon; the advanced
    search entry is a filter icon beside the search field.
  - D (done): a Memories year row on phone Home (`MemoryYearCard`, unchanged) below the destination
    shelves, and one fallback "recent" `HomeShelf layout="rows"` (songs → recently added, sets → recently
    released) when neither of those two destinations already draws its own shelf.
  - E (done): a "Recent" row (`RecentPlacesRow.svelte`) above Browse's category grid, one
    `QuickAccessTile` per artist/album/genre/label/festival/playlist/preset/year/memories opened on
    this device and account (`recentPlaces.js`, `localStorage`, capped at 12, newest first); the
    player header names the place the queue actually started from (`queue.js`'s `startQueue`,
    `store.js`'s `queueSource`) instead of always the current track's album.
  - F (done): three sections below the full-screen player's bottom icon row, each hidden with
    nothing to show: "Next up" (`nowPlaying.nextUp`, the three entries after `Player.svelte`'s
    `queueIndex` in `$playlist`, or one line when shuffle is on), "More from {artist}"
    (`nowPlaying.moreFrom`, six tracks lazily fetched once per `artistId` and cached across a
    close/reopen), and "Other versions" (`track.versions`, via the shared `loadVersions()` in the
    new `versions.js`, also used by `SongView.svelte`'s own page). Rows are `TrackRowCompact`; an
    `onplay` override makes a "next up" tap jump within the playing queue while the other two
    sections start a fresh one (`queue.js`'s `startQueue`). `addAfterCurrent` inserts at
    `queueIndex + 1` instead of searching `$playlist` for the track's id, which used to land on
    the wrong copy when the same track appeared twice in the queue. The screen now actually
    scrolls, so the swipe-to-close gesture only fires with the container scrolled to the top.
  - G (done): two horizontal `QuickAccessTile` strips below the fallback recent shelf on phone
    Home, "Jouw artiesten deze maand" and "Jouw labels" (`homeRankings.js` over
    `/api/listening/top-artists`/`top-labels`), each with a "Alles tonen" to the listening-stats
    page; hidden together with no fetch at all when the account has no MuMa key, and per-row when
    its ranking is empty. An artist tile resolves the LMS `artist:<id>` via `search3` before
    navigating (MuMa's own `artist_id` is a different id space) and falls back to `search:<name>`
    when nothing matches; a label tile opens `label:<name>` directly, same as `RecentPlacesRow`.
  - H (done): the output the phone plays through ("Bose QC35 II", "Bedrade koptelefoon",
    "Telefoonluidspreker") as a `text-brand` 13px bold line with an 18px glyph per kind
    (Bluetooth / headset / speaker) directly above the full-screen player's bottom icon row;
    tapping opens Android's output switcher, or Bluetooth settings without one. Native only:
    `platform.system.outputRoute()` is `null` in a browser and the line is not rendered.
    Since I it is the left end of the bottom icon row.
  - I (done, 2026-09-24): the full-screen player is a one-screen stage -- only the cover shrinks,
    the transport is always visible; artists on one truncating line; album left and release date
    right-aligned (`tabular-nums`) on one line, no `·`; genre/label chips on one sideways-scrolling
    row; the transport's outer glyphs aligned to the text edge (`-mx-2`) (the stars were too, with
    `-ml-2.5`, until J); landscape is two columns (cover left, info right), portrait tablets a
    centred `max-w-xl` column. The song table shows optional columns by its own width (container
    queries), truncates cells, never wraps the date, and has no rating column on touch devices.
  - J (done, 2026-09-24): the full-screen player's rating row is **centred**, not aligned to the
    text edge: five 44px targets spread evenly (`justify-between`) over a centred `max-w-xs`
    (320px) row, so it shares the transport row's centre line and does not stretch on a tablet.
    Glyphs are 28px, the size of the previous/next glyphs. A set star is filled `text-brand`; an
    unset star is a 1.5px outline in the secondary grey `#B3B3B3` -- "no rating yet", never the
    faded `white/10` fill that read as disabled. Scope: `NowPlaying.svelte` only; the desktop bar,
    track rows and the details sheet keep their own compact stars.
  - K (done, 2026-09-24): the full-screen player's bottom icon row carries the news of the hour
    button directly after the radio button, styled like it: 24px newspaper glyph (the desktop
    bar's), `#B3B3B3` idle, `#b266ff` while a bulletin plays, `aria-pressed` (bug report 059).
  - L (done, 2026-09-24): meta chips are coloured **by kind, never by position**. `MetaChips.svelte`
    reads `kind` per item. A genre chip (and any chip without a kind: festival, mood) keeps the
    neutral chip -- `bg-muma-spotify-light text-muma-spotify-text`, hover `bg-muma-spotify-hover text-white`. A label chip is a
    muted amber: `bg-[#3a2c16] text-[#ffcc80]`, hover `bg-[#4a3820] text-[#ffe0b2]` (contrast about
    9:1), so genres and label read apart at a glance on the player's sideways chip row. Not the
    brand token (the mode accent that marks active states), not `#b266ff` (radio/news active), not
    a blue (sets mode's brand): each of those already means something else. Applies wherever
    `MetaChips` renders a label -- the full-screen player and the track details sheet.

- **Done** (2026-09-25, `docs/designs/track-form/`) — a **Soort** (form) filter in the sets view's filter
  bar. No new style: on the phone it is one more `filterChip` (neutral when unset, `bg-brand
  text-black` with a clear button when set) opening a `BottomSheet` listbox -- Alle, Sets & mixes,
  Livesets, Podcasts -- placed directly after the year chip; in the desktop bar it is one more
  labelled `<select>` in the same row, same classes as the year select. Only in the sets view: in
  the songs view every row is a track, and a picker with one real choice is noise.

- **Done** (2026-09-26, issue #47) — the same **Soort** choice in the preset builder and in Android
  Auto. No new style: in `PresetBuilder.svelte` it is one more labelled `<select>` with exactly the
  classes of the Sortering select, shown only in sets mode; in the car it is one more row in the
  Sets tab's Bladeren group (text row, like Jaren), leading to three plain folder rows. MuMa Voice's
  explanation card gets a "Soort" row in the existing row layout.

- **Done** — Android login/welcome screens brought in line with the web's `LoginPage.svelte`: filled/rounded
  dark inputs (`MuMa Mobile.TextInputLayout`), a solid-green pill CTA
  (`MuMa Mobile.Button.Primary`), a branded white "Sign in with Google" pill button with the real
  Google "G" logo (`MuMa Mobile.Button.Google`), a hairline-flanked "OF" divider, a `spotify_light`-background
  rounded dialog card (`ThemeOverlay.MuMa Mobile.WelcomeDialog`, scoped to this one dialog only via the
  `MaterialAlertDialogBuilder` theme resId), and a circular avatar on the Google access-request screen
  (`google_auth_fragment.xml`).
- **Done** — Android filter/search panel (`muma_filters.xml`, `muma_search.xml`,
  `filter_button_bar.xml`) had its buttons, the favorite-star icon tint, and the "show filters" FAB
  hardcoded to `design_default_color_primary_dark` (a generic Material default color, not a brand token) -
  an actual style-guide violation ("Don't introduce unauthorized color palettes"). Recolored to
  `spotify_green`, and the filter panel/popup background (`rounded_background_popup.xml`, previously a
  hardcoded `#333333`) and the filter bar container (`filter_button_bar.xml`) now use the `spotify_light`
  (`#181818`) token per the Filter Bar component spec above, instead of the hardcoded gray/card color.
- **Done** — Android home screen loading states: per-section skeleton placeholders
  (`home_skeleton_carousel.xml`, `home_skeleton_grid.xml`, `@drawable/skeleton_block`,
  `@anim/skeleton_pulse`) per the Loading States section above, plus a "Log out" entry in the
  toolbar overflow per the Session controls component rule.
- **Not yet done** — track-row/list-item tap feedback (the style guide's `bg-white/10` hover-state pattern)
  wasn't added in this pass: `list_item_track.xml`'s row background has no ripple/press state today, and the
  existing `default_ripple.xml`/`select_ripple.xml` drawables reference a `?attr/backgroundColor` that isn't
  a standard theme attribute in this app, so wiring one in without being able to visually verify it felt too
  risky for this pass. The rest of the Android UI (track/album cards, player, navigation) also hasn't been
  brought in line with this style guide's component patterns -- and then, since muma-mobile 7.0.0, the
  Android UI is the web player itself (`docs/designs/universal-ui/`), so this paragraph is history.

- **Done** — Phone feedback round 3 (2026-09-15). Settings share compact density: p-4/gap-4,
  text-base section headings, text-sm font-medium row titles, text-xs help. Home quick-access
  tiles use two columns, a 48px cover/colour block, bold title and truncated subtitle on #282828.
  Favorites reuses those tiles for presets in its own two-column grid, below the create action;
  the bottom bar is Home / Browse / Favorites, with Playlists offered in Browse.
  Track overflow opens the existing BottomSheet with metadata, stars and full-width action rows;
  three-line track rows retain album links and touch-accessible rating controls.
