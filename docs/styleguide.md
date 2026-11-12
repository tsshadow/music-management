# 🎨 Music Management System Style Guide

## Theme & Brand
- **Theme**: Dark (immersive dark mode optimized for music streaming, long-term listening, and management).
- **Brand Personality**: Sleek, modern, efficient, music-centric, professional yet accessible.
- **Tone and Voice**: Clear, concise, modern, helpful, direct.
- **Design Principles**:
  - Immersive dark aesthetic that highlights cover art and media.
  - Consistent layout paradigms across Web UI (`services/frontend`) and Android mobile (`services/muma-mobile`).
  - Generous whitespace and clean information hierarchy.

## Colors
- **Primary Accent**: `#1DB954` (brand green) — Primary actions, active states, highlights, playback indicators.
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
  - Success: `#1DB954` (brand green)
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
  - **Hover-revealed actions** (a card's round play button): hidden until hover only with a mouse.
    On a touchscreen there is no hover, so the action is always visible and at least 48px
    (`pointer-coarse:opacity-100 pointer-coarse:translate-y-0 pointer-coarse:w-12
    pointer-coarse:h-12`), and keyboard focus reveals it too (`focus-visible:opacity-100`). Key it
    on the pointer, not on the layout: a tablet in the desktop layout is still a touchscreen.
    `DailyMixCard` follows this (issue #99).
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
  and `common.loading` while the next page is on its way. It never shows a count or a page number.
  Once a list that did continue has nothing more, the pill is replaced by one centred line in the
  muted text colour (`text-muma-spotify-text text-sm py-6`), `common.endOfList` ("Einde van de
  lijst"); a list that fit on one page shows neither. Pill and end line are one component,
  `ListEnd.svelte`, so a page and the queue cannot drift apart. Used by the song, artist and album
  lists, the search results, presets, the listen history and the feed pages
  (`docs/designs/feed-length/`, `docs/designs/list-continuation/`). A queue started from any of
  these lists tops itself up near its end, and the queue list (the bottom sheet on the phone and the
  tablet, the side panel on the desktop) ends in the same pill while its list has a next page and in
  the end line once it ran out (`QueueLoadMore.svelte`). The Now Playing screen itself gets no
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
- **First-run server screen** (app only, `FirstRunServer.svelte`, issue #192): the login page's
  card layout and its fixed `brand-green` accent (the login page's exception to the brand token).
  One address field in the login page's field style, the example address in muted `text-[11px]`
  under it, "Verbinden" as the primary pill. A refused check is one line in the login page's error
  box (`bg-[#e91429]`); a check in progress is the button spinner plus a muted `text-xs` line, with
  the field disabled. "Toch doorgaan" (MuMa did not answer) and "Opnieuw proberen" (no network) are
  secondary pills (`bg-muma-spotify-hover`) under the form. Opened to change the server, it has a
  muted "Annuleren" text link at the bottom.
- **Server line on the login page** (app only): where the server field was, one muted `text-xs`
  line "Server: <host>" with "Wijzigen" as a text link after it. Settings > Apparaat starts with a
  "Server" row of the same shape; a change to another server asks first with the Confirmation
  dialog.
- **Session controls**: "Log out" lives in the overflow/secondary menu (Android: the toolbar
  overflow, directly above "Exit"), never as a primary action. It always confirms first, stating
  what is lost (playback stops) and what is kept (downloads), and it returns the user to the login
  screen rather than to an empty app. On the web and in the app (the same web UI) that
  confirmation is a Confirmation dialog, see below; the line about downloads only shows in the app,
  since a browser tab has none (issue #80).
- **No-connection notices** (`OfflineNotice.svelte`): a centred block on a faint surface
  (`bg-white/5`, `border-white/5`, `rounded-xl`, `p-12`), a 48px icon at 20% opacity, a bold white
  title and a muted one-line help text, never a spinner. `unavailable` and `empty` are for the
  offline library; since issue #72 two more stand above the content when the player is signed in
  but has no Subsonic token and so requests nothing: `server` ("De server geeft geen toegang",
  with an "Opnieuw proberen" retry) and `signIn` ("Log opnieuw in", with an "Opnieuw inloggen"
  button that ends the session and shows the login page). Their buttons are the outlined pill of
  "Load more" above. The car shows the same two messages as Media3 session errors.
- **Pickers (search-as-you-type)**: `MultiPicker.svelte` collects several names as chips;
  `SinglePicker.svelte` picks exactly one *record* (an id, not free text) and is the same control:
  the uppercase `text-xs` label, the `bg-muma-spotify-light rounded-md` field with the brand focus
  outline, and the same suggestion list under it (`bg-muma-spotify-light rounded-md shadow-xl
  border border-white/5`, rows `px-3 py-1.5 text-sm` with `hover:bg-white/10`, a muted second
  line per row when a suggestion needs context such as platform and track count). Suggestions are
  asked from the server 200 ms after the last keystroke. Once picked, the field shows the choice as
  one chip (`bg-white/10 rounded-full`) with an × to pick again; Enter never submits free text.
  Used by the hand-link panel on Management > Downloaders > Links
  (`docs/designs/channel-links/`).
- **Curation state badges** (Management > Curatie tables): a small uppercase label
  (`text-[10px] font-bold uppercase px-2 py-0.5 rounded`) under the name. Approved is brand
  (`bg-brand/20 text-brand`), rejected is red (`bg-red-500/10 text-red-500`), and *pending* --
  a name the tagger does not trust yet (artist curation, "Nieuw") -- is yellow
  (`bg-yellow-500/10 text-yellow-500`), the colour the queue's own "to review" icon already uses.
  A badge states a fact about the row; it is never the only way to act on it.
- **Station tile**: one live station in a grid of 3 columns on a phone, 5 from `md`, 7 from `xl`. The logo
  has an 8:5 ratio and `rounded-md`, with the name under it (`text-[12px] font-bold`). The station that
  plays has `ring-2 ring-[#b266ff]` and a name in the same color, the radio color. The star is a 32 px
  round button at the top right of the logo (`bg-black/60`, `text-brand` when marked), so the action is on
  the tile and not in a menu. In the full player a logo uses `object-contain` on black, because a logo must
  not be cut to the square of a cover. A station without a logo file shows its name on the tile.
- **Compact player** (`CompactPlayer.svelte`, `docs/designs/miniplayer/`): the player in a small
  box, on the panel color (`bg-muma-spotify-panel`). Below 200px high it is a strip: the square
  cover at the full height on the left, then the title (`text-[13px] font-bold`), the artist in
  muted `text-[11px]`, and one row with previous, the white round play button (36px), next, and the
  stars (12px, `text-brand` when set) at the end of that row. From 200px high the cover goes on
  top. A 2px progress line (`bg-white` on `bg-white/10`) runs along the bottom edge. No
  transitions and no animation. A live station drops skip, stars and progress. The PC window
  (issue #177) is the first user.
- **Miniplayer button** (desktop player bar, Chrome and Edge only): the lucide `PictureInPicture2`
  icon at 16px, in the right cluster before the queue button, with the same muted-to-white hover as
  its neighbors. A browser that cannot open the window does not show it.
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
- **Wrapped card** (`src/lib/wrapped/`): one card holds one small uppercase label, one headline,
  one sentence and at most one chart or list. Phone width: each card is at least `min-h-[100dvh]`
  and the card run scrolls with `scroll-snap-type: y mandatory`, `snap-start` per card. From `md`:
  a two-column grid with `gap-4`, no snap, the title card `md:col-span-2`. The headline is
  `font-black`, `text-5xl` (a number or a name, `md:text-7xl` on the title card). A card led by a
  genre (top genres, new genres) has that genre's tint fading into `muma-spotify-dark`
  (`linear-gradient(160deg, <tint>, #121212 70%)`); every other card is `bg-muma-spotify-panel`
  with `brand` bars and accents. Bars are divs like Listening stats, and each value is also
  text. The User / Library tabs are two `<button aria-pressed>` pills in the chip style
  (`bg-brand text-black` when picked, else `bg-muma-spotify-light text-white`). The share button
  is a round 40px icon button (lucide `Share2`) in the card's top right corner. The share image is
  1080 x 1920: the same tint or panel color, the label, the headline, the sentence, the period
  and the MuMa mark, never a username or a server address.

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
- **A page whose code is still loading** (web, issue #114: pages off the first screen are separate
  chunks, `LazyView.svelte`): 8 `SkeletonRows` in the content area while the chunk loads, and the
  section error with "Opnieuw" if it fails. Overlays, sheets and sidebars show nothing meanwhile —
  a skeleton would only flash. Opened by URL, the boot screen stays up until the page's chunk is
  in, so the app never appears with a skeleton in place of the page.
  The artist and album pages (issue #118) instead show their header drawn from what the tapped
  link knew -- picture, kind line, the name as the heading, placeholder play buttons -- with the
  page's own classes, and 8 `SkeletonRows` below (`EntityPageShell.svelte`), so the heading is
  there at once and nothing moves when the page's code arrives. A grid page (genres, labels ...)
  shows `SkeletonTiles`; the filter and collection bars show nothing for that moment.
  A settings tab (issue #119: one chunk per tab) shows the tab's own shape in skeleton blocks --
  a title and subtitle bar, then two panels of label-and-toggle rows, with the settings density
  classes (`SettingsTabSkeleton.svelte`) -- never skeleton track rows, which are not what a
  settings page looks like. The full-screen Now Playing (issue #119) never shows a skeleton page:
  until its code is in, `NowPlayingShell.svelte` draws the same screen from what the mini player
  knows -- the tinted background, the header with "Afspelen vanuit", the cover, title, artist and
  album, and a working play/pause button -- with the rating, the progress bar and the other
  transport buttons as skeleton blocks of the same size. It flies in like the real view; the real
  view replaces it without a second animation. A chunk that fails shows the section error with
  "Opnieuw" under the header, which still closes the screen.
- **New place, new rows**: a list that opens for a different thing (another genre, label,
  festival, search term) never shows the previous thing's rows, not even for one frame: it clears
  and shows skeletons, or shows its own cached rows. Only the same list under changed filters keeps
  its rows, as stale results (below).
- **Stale results**: rows that belong to the same list under the previous filters stay on screen
  at `opacity-50` (200 ms `transition-opacity`) until the new answer replaces them, with an inline
  throbber next to the heading. Never an empty-state message ("Geen resultaten") while an answer is
  still on its way: "nothing" is only said about an answer.
- **Search as you type**: from the first keystroke (the debounce included) the results panel shows
  a "Zoeken…" line with an inline throbber in secondary text. With nothing to show yet, three
  skeleton rows follow it; with the previous text's results, those stay, dimmed as stale results.
  A failed search shows the section error with "Opnieuw", never "Geen resultaten gevonden".
- **Web tokens**: the placeholder colour is the `muma-skeleton` token (`bg-muma-skeleton`) and the
  pulse is the `skeleton-pulse` class in `src/app.css` (it stops under `prefers-reduced-motion`).
  Use `Skeleton.svelte` for a single block, `SkeletonRows.svelte` for track rows (TrackList
  geometry: `h-14 md:h-16`, 48px cover, two text lines) and `SkeletonTiles.svelte` for a card grid.
  Never write "Loading…" text as the only content of a page.
- **Boot screen** (web and app): from the very first frame, `index.html` shows the MuMa mark
  centred on `#191414`, with a status line under it in secondary text (`#B3B3B3`, 14px). The status
  line names the stage ("Verbinden…", "Inloggen…"). The app does not wait for the queue restore
  here any more (issue #113): the mini player shows it instead, see "Mini player: restoring the
  queue". Under it runs a 3px
  progress bar, 160px wide and `rounded-full`, in the brand green on a `#2F2F2F` track. The bar is
  indeterminate (a sliding segment) unless the stage has a count, in which case it fills. After 8 s
  on one stage a muted line (`#727272`, 12px) says it is taking longer than usual. After 20 s
  without the app, an outlined "Opnieuw proberen" pill reloads the page. The screen fades out
  (200 ms) once the app is mounted. It is never shown again during the session.
- **Boot screen: server unreachable** (app only, docs/designs/app-start-reachability/): when a
  signed-in phone cannot reach its server, the stage line, bar and hints make way for a panel on the
  same `#191414` screen, centred under the mark, at most 320px wide. A white 18px bold title names the
  problem ("Geen netwerkverbinding" / "Server niet bereikbaar"), a 14px secondary line (`#B3B3B3`)
  says what can be done, and a muted 12px status line (`#727272`) says what is happening ("Verbinding
  controleren…"). Under it, three full-width pills stacked 12px apart, each at least 48px high: the
  primary white-filled "Opnieuw proberen", then the outlined "Wachten op server" and "Offline verder"
  (1px `#727272` border, white text). While a check runs the first two are disabled at 50% opacity.
  Waiting swaps the title to "Wachten op de server", the secondary line to "Wachten sinds 14:03" and the
  status line to "Volgende poging over 5 s", and hides the "Wachten" pill; there is no spinner and no
  error text in this state.
- **Offline mode banner** (app only): after "Offline verder", a strip at the top of the content area on
  every page, `bg-muma-spotify-light`, `rounded-md`, `px-4 py-3`, 14px. The offline icon (20px,
  secondary text colour) on the left; a bold white line "Offline: alleen muziek op dit toestel" and,
  when queued tracks were left out, a secondary line "12 nummers niet beschikbaar offline"; on the right
  an outlined `rounded-full` "Opnieuw verbinden" pill (48px touch target) that shows the inline
  throbber while it checks. It disappears by itself when the server answers, and a success toast says
  "Weer verbonden".
- **Optimistic page shell**: a page that opens a thing (artist, album, feed, a song's versions...)
  renders its header at once from what the tapped link already knew: name, picture and action
  buttons. Only the sections
  that still need data show skeletons. Opened by URL with nothing known, the header itself is a
  skeleton, a round or square picture block and a title bar, with the same geometry as the real
  one. Server data always replaces what the link knew.
- **Section errors**: a section that fails shows one muted line ("Kon dit deel niet laden") and the
  outlined Load-more pill labelled "Opnieuw", in place of its content. The rest of the page stays.
- **Inline throbber**: `Throbber.svelte`, a 16px ring in `currentColor`, spinning. It marks an
  action that is waiting (a play button pressed before its tracks arrived) or a background refresh
  next to a section heading. It never replaces a whole page or section: that is what skeletons are
  for.
- **Play button: buffering** (web player and app): while a play request waits for data, at the start of a
  track, after a seek into a part not loaded yet or when the network falls behind, the play/pause
  button shows the inline throbber in place of its icon. The size is 24px in the mini player's
  32px icon box, 16px in the white circle of the desktop player bar, and 28px in the Now Playing
  circle. The ring takes the button's own color, white or black. The button keeps its pause label
  and still pauses. The icon comes back when the audio plays again or the listener pauses. In the
  app the playback service reports it: Media3 buffering while it is set to play.
- **Mini player: restoring the queue** (app only, issue #113, docs/designs/deferred-queue-restore/):
  while the queue the phone's player holds is still being looked up after the app opened, the mini
  player shows, in place of "Niets aan het afspelen", its 44px cover slot as a `bg-muma-skeleton`
  square (`rounded`) holding the inline throbber at 20px in secondary text, and the line
  "Wachtrij wordt hersteld…" in secondary text, 13px, medium weight, not italic. The play/pause
  button stays and works; next, the stars and the progress bar are hidden as with no track. The wide
  player bar (a tablet) shows the same in its 56px cover slot at 14px. When the restore finishes
  the row becomes the playing track without an animation; when the listener starts a track first,
  that track replaces the row.

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
  | `muma-skeleton` | `#2F2F2F` | loading placeholders (skeletons, boot-screen bar track) |

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

- **Done** -- Wrapped cards (2026-11-12, issue #60, `docs/designs/wrapped-page/`, approved with
  the design): see "Wrapped card" under Components. No new token.

- **Done** -- Compact player and the PC miniplayer window (2026-11-12, issue #177,
  `docs/designs/miniplayer/`): see "Compact player" and "Miniplayer button" under Components. No
  new token. The phone's split-screen and picture-in-picture variants (#179, #178) reuse it.

- **Done** — First-run server screen and server line (2026-11-10, issue #192,
  `docs/designs/first-run-server/`): see "First-run server screen" and "Server line on the login
  page" under Components. The settings row and the switch dialog reuse the Apparaat rows and the
  Confirmation dialog.

- **Done** — Correct a BPM by hand (2026-09-30, `BpmOverride.svelte`): no new token or component
  style. Shown only with the `bpm.override` permission, under the BPM tile of the management
  library's track inspector and under the tag list of the player's details sheet. A small uppercase
  caption like the inspector's tile labels, then "½×" and "2×" -- and "Gemeten" only when the tempo
  is manual -- as the inspector's secondary pills (`text-xs font-bold bg-white/5 hover:bg-white/10
  border border-white/10 rounded-full px-3 min-h-8`, `disabled:opacity-50` while a request runs),
  then a Forms & Inputs field (`w-20 bg-muma-spotify-light rounded`, `focus:border-brand`) with a
  "Zet" pill. A refusal is one `text-xs text-red-400` line under it. A manual tempo is marked with
  the BPM pill of the BPM browse list (`text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/10
  text-muma-spotify-text`) reading "handmatig".

- **Done** — GetSongBPM attribution (2026-11-10, issue #152, `docs/designs/getsongbpm-prior/`): when
  GetSongBPM's tempo helped choose a measured BPM, the BPM row in the player's track details ends in a
  plain muted link "via GetSongBPM" (`ml-1 text-[10px] text-muma-spotify-muted hover:text-white
  hover:underline`) to getsongbpm.com, opened in the system browser like the source URL. No pill, no
  icon: it credits a source, it is not a state of the track.

- **Done** — Browse by BPM in Android Auto (2026-09-30, issue #140, `docs/designs/android-auto-bpm/`):
  no new style. One more text row ("BPM") in the Nummers tab's Bladeren group, after Lineups,
  leading to ten plain folder rows ("150 BPM", "210+ BPM") with the track count as the row's
  subtitle, and each of those to the usual "Alles afspelen" plus track rows. No artwork, so the
  car draws a list, not a grid.

- **Done** — Browse by BPM (2026-09-29, `docs/designs/bpm-browse/`): no new token or component.
  Its Bladeren tile takes the fixed tile colour `#006450` (`browseColors.js`, the one new value;
  the tile table is a set of fixed category colours, not tokens).
  The page (`BpmView.svelte`) is built like the listening statistics page: a `bg-black/40
  rounded-xl border-white/5` filter card, then a chart card, then the list. Tempo chips are the
  neutral chip (`bg-muma-spotify-light text-white`, hover `bg-muma-spotify-hover`, `rounded-full
  text-xs font-bold min-h-9`) and `bg-brand text-black` when picked, with their count in the chip's
  muted text. The margin selector is the period selector (`bg-black/40 rounded-full p-1`, the picked
  option `bg-brand text-black`). The from-to range and the genre `<select>` are Forms & Inputs
  (`bg-muma-spotify-light rounded-md min-h-11`, brand focus outline). "Betrouwbaar" is a chip-shaped
  `<button aria-pressed>` with the lucide `ShieldCheck` icon. The histogram reuses "a chart bar is
  its own filter toggle": one `<button aria-pressed>` per whole BPM, `bg-brand/50`, hover
  `bg-brand/80`, the bars inside the picked window `bg-brand`. A row's BPM is a small pill after the
  title in `TrackList` (`text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded bg-white/10
  text-muma-spotify-text`), "≈152 BPM" for a coarse value; the one line explaining "≈" sits above
  the list in `text-xs` muted text with lucide `Info`, never a banner or dialog.

- **Done** — Listening statistics filters and breakdowns (2026-09-29,
  `docs/designs/listening-stats/`): no new token or component. The genre filter is the existing
  `MultiPicker`; the year range is two inputs in the Forms & Inputs style (`bg-muma-spotify-light
  rounded-md min-h-11`, brand focus outline). New *pattern*, built from existing tokens: **a chart
  bar is its own filter toggle** -- every bar is a `<button aria-pressed>`, unselected
  `bg-brand/50` (hover `bg-brand/80`), selected `bg-brand`; a horizontal-bar row also gets
  `bg-white/5` when selected, and the chart ends in one muted line saying a tap toggles it. Active
  filters that are not already shown in their own control (single years, "Onbekend jaar", the range)
  are `bg-brand text-black` chips with an ×, followed by the outlined "Filters wissen" pill of
  "Load more" in `text-xs`. A notice about what a filter excludes sits directly under the filter in
  `text-xs` with the yellow `TriangleAlert` of the page's caveat box, not in a footnote. The
  Jaar/Decennium switch is the page's period selector at `text-[10px]`.
- **Done** — Feed length (2026-09-26, `docs/designs/feed-length/`): no new token or component. The
  existing load-more pill is documented above under Components ("Load more") and reused as-is under
  a feed's track list.
- **Done** — List continuation (2026-09-27, `docs/designs/list-continuation/`, issue #100): no new
  token. Every paged list continues in the queue with the existing load-more pill; the new "Einde
  van de lijst" end line uses only the muted text colour. Documented above under Components ("Load
  more").
- **Done** — Feed "Meer laden" in the queue (2026-09-27, bug report 122): no new token. The same
  load-more pill under the queue list for a feed queue, and a muted "not found on the server" note
  in the feed header meta line, both documented above under Components ("Load more").
- **Done** — Versies page in Management (2026-09-26, `docs/designs/song-versions/`): built only from
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
- **Done** — Android filter/search panel (the filter and search layouts and
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

- **Done** (2026-09-27, issue #107) — Perceived performance on the web and in the app: the boot
  screen, skeleton placeholders on the web (`muma-skeleton`, `skeleton-pulse`,
  `src/lib/loading/`), the optimistic page shell for the artist and album pages, section errors
  with a retry, and the inline throbber, as described under Loading States above
  (`docs/designs/perceived-performance/`). The other entity pages (genre, label, festival, feeds,
  track versions, search) follow in their own issues and use the same components.

- **Done** (2026-09-27, issues #110, #111, #99) — The feed pages (release radar, daily mixes) and
  the song versions page use the optimistic page shell: the header from the tapped card or row,
  skeleton rows under the rows that have already landed, and a section error with "Opnieuw" per
  failed part. The song page's header gains the cover (`w-28 md:w-40`, `rounded-md`, the album
  header's shadow) on the left of the title. The daily mixes page shows card-shaped skeletons
  (`h-[150px] rounded-lg`) in its grid, and the track details sheet shows key/value skeleton rows
  for the tags. Daily-mix cards follow the Hover-revealed actions rule under Cards.

- **Done** (2026-09-27, issue #122) — The label page's **Kanalen** section
  (`LabelChannels.svelte`): a `text-base font-bold` heading, then one sideways-scrolling row
  (`overflow-x-auto`, never widening the page) of channel cards -- `h-14`, `max-w-64`, `rounded-md`,
  `bg-muma-spotify-light`, hover `bg-muma-spotify-hover`, a 20px platform icon in secondary text
  (lucide `Cloud` for SoundCloud, as the downloader tabs already use; `TvMinimalPlay` for YouTube;
  `Send` for Telegram; no brand logos), the name in bold white and the track count in `text-xs`
  secondary text. Its skeleton is three card-sized `Skeleton` blocks, shown only where the section is
  certain to appear (to a curator): a placeholder on every label page that then vanishes would move
  the track list. The curator's way to Links is a text button in the heading row (`text-xs
  font-bold`, secondary text, hover white, `Link2` icon), on the element it concerns rather than in a
  menu.

- **Done** (2026-11-10, issue #126) — The same section on the artist page (above the biography) and
  on the label edit page. On the edit page every card gets a `w-10` unlink button on its right edge,
  inside the card's background: lucide `X` at 16px in secondary text, hover white on
  `bg-muma-spotify-hover`, labelled "<channel> ontkoppelen". It acts without a confirmation dialog,
  as the `X` on a link chip in the Coverage table does, because linking again is one step; the card
  dims while the request runs.

- **Done** (2026-09-27, issues #109 and #112) — The genre, label, festival, podcast, year and
  lineup lists and the search results page, dropdown and "more" modal follow Loading States: new
  place clears to skeletons, same place dims stale results, search says "Zoeken…" until it has an
  answer, and History, Starred and Memories load as skeleton sections.

- **Done** (queue position) — A queue row shows its place in the play order, "3/500", right-aligned
  on the artist line (`text-xs text-muma-spotify-text tabular-nums`, `min-width` set from the
  widest position so the artist does not shift). The date moves to the right end of the album line.
  The Now Playing screen shows the same text (`text-sm`) right-aligned on its artist line, when the
  track sits in the queue. Other track lists have no position.
