# 🎨 Music Management System Style Guide

## Theme & Brand
- **Theme**: Spotify Dark (immersive dark mode optimized for music streaming, long-term listening, and management).
- **Brand Personality**: Sleek, modern, efficient, music-centric, professional yet accessible.
- **Tone and Voice**: Clear, concise, modern, helpful, direct.
- **Design Principles**:
  - Immersive dark aesthetic that highlights cover art and media.
  - Consistent layout paradigms across Web UI (`services/frontend`) and Android mobile (`services/ultrasonic`).
  - Generous whitespace and clean information hierarchy.

## Colors
- **Primary Accent**: `#1DB954` (Spotify Green) — Primary actions, active states, highlights, playback indicators.
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
  - **Android UI (Ultrasonic / Mobile)**:
    - Compact touch targets (minimum 48x48dp).
    - Bottom navigation bar or hamburger menu for navigation.
    - Single-column lists or compact 2-column grids for track and album browsing due to limited screen width.
- **Margins & Padding**: Generous spacing around major UI blocks to prevent clutter.

## Components
- **Buttons**:
  - Primary: Rounded full (`rounded-full`), Spotify green background (`bg-[#1DB954]`), dark text or white bold text.
  - Secondary: Transparent with border or surface gray background (`bg-[#282828]`), white text.
- **Forms & Inputs**: Dark background (`bg-[#282828]`), subtle border, green focus ring (`focus:border-[#1DB954]`), white text.
- **Cards**: Surface gray (`bg-[#282828]`), rounded corners (`rounded-md` or `rounded-lg`), smooth hover elevation/scaling.
- **Modals**: Centered overlay with backdrop blur or dark translucent background (`bg-black/80`), rounded card container.
- **Navigation**: Persistent sidebar on Web, Bottom Navigation / Drawer on Android. Active items highlighted with white text and/or green accent.
- **Session controls**: "Log out" lives in the overflow/secondary menu (Android: the toolbar
  overflow, directly above "Exit"), never as a primary action. It always confirms first, stating
  what is lost (playback stops) and what is kept (downloads), and it returns the user to the login
  screen rather than to an empty app.

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
- **Web (`services/frontend`)**: Svelte components + Tailwind CSS utility classes adhering to the Spotify dark color tokens (`spotify-green`, `spotify-gray`, etc.).
- **Android (`services/ultrasonic`)**: Kotlin + Material Design components customized with dark theme color attributes matching the web palette.

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
3. **Code Implementation**: Once documented, implement the approved styles in code (`services/frontend` or `services/ultrasonic`), then mark the item as completed in the style guide.

### Design Backlog

- **Done** — Android login/welcome screens brought in line with the web's `LoginPage.svelte`: filled/rounded
  dark inputs (`Ultrasonic.TextInputLayout`), a solid-green pill CTA
  (`Ultrasonic.Button.Primary`), a branded white "Sign in with Google" pill button with the real
  Google "G" logo (`Ultrasonic.Button.Google`), a hairline-flanked "OF" divider, a `spotify_light`-background
  rounded dialog card (`ThemeOverlay.Ultrasonic.WelcomeDialog`, scoped to this one dialog only via the
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
  brought in line with this style guide's component patterns; see `services/ultrasonic/STYLEGUIDE.md` for the
  full reference these should eventually follow.
