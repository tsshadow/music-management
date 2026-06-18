### Proposal: Unified UI for Songs and Sets

#### 1. Core Concept
The UI will shift from having a separate "Sets" page to a unified "Library" view that can be toggled between "Songs" mode and "Sets" mode globally. This toggle will affect data filtering, branding colors, and navigation.

#### 2. Feasibility
**Is it possible?** Yes, absolutely. The current implementation already uses identical logic for both views, differentiated only by a `minDuration`/`maxDuration` filter.

#### 3. Required Changes

##### State Management (`src/lib/store.js`)
- Add a new persistent store `viewMode` (values: `'songs' | 'sets'`).
- Add a derived store `themeColor` that returns green for songs and blue for sets.

##### UI/UX Components
- **TopBar.svelte**: Add a prominent toggle button (e.g., a "Switch to Sets/Songs" button or a pill-style toggle).
- **Sidebar.svelte**: Remove the dedicated "Sets" menu item. The "Songs" item can remain as the primary entry point to the library, which now respects the global `viewMode`.
- **Dashboard.svelte**: 
    - Update `loadAllTracks` to use `$viewMode` instead of `activeView === 'sets'`.
    - Ensure that when `viewMode` changes, `loadAllTracks()` is re-triggered and the `tracks` array is cleared to avoid mixing content.
- **ArtistView.svelte**:
    - Update to respect the global `viewMode`. Instead of loading both "Tracks" and "Sets" and showing them separately, it should prioritize the current mode or only show the relevant section.
- **Dynamic Styling**:
    - Update `app.css` to use CSS variables for the primary brand color (e.g., `--brand-color`).
    - Update components to use this variable instead of the hardcoded `spotify-green`.
    - Apply a global class or attribute to the body (e.g., `data-mode="sets"`) to allow easy CSS overrides for the blueish theme.

#### 4. Styling (Colors)
- **Songs Mode**: Current Spotify Green (`#1db954`).
- **Sets Mode**: A complementary blueish color, e.g., Spotify Blue (`#2d5afc`) or a deep sky blue (`#00aaff`).

#### 5. Logic Updates
- **Genre Views**: When a user clicks "Raw Hardstyle" in the sidebar, the view will show either "Songs" or "Sets" depending on the global toggle.
- **Home View**: The "Songs" and "Sets" sections on the home page can either:
    - Remain as they are (curated snapshots).
    - Or be replaced by a single "Discover" section that respects the mode.

#### 6. Pitfalls & Considerations
- **State Transition**: Ensure that switching modes while on a specific genre/artist page correctly reloads the content for that specific context.
- **Deep Linking**: The URL structure should ideally reflect the mode (e.g., via a query parameter or a prefix) so that sharing a link to a "Sets" view works as expected.
- **User Confusion**: Make the toggle very clear. If the whole UI changes color, it's a strong visual cue, but a text label ("Viewing Sets") might still be needed.
- **Mixed Content**: Decide if "Albums" and "Playlists" should be filtered by the mode. (e.g., Should "Albums" only show DJ Mixes/Sets in Sets mode?)

#### 7. Implementation Plan
1. **Define Stores**: Add `viewMode` to `store.js`.
2. **Abstract Colors**: Move `#1db954` to a CSS variable in `app.css`.
3. **Add Toggle**: Implement the mode switcher in `TopBar.svelte`.
4. **Update Data Logic**: Refactor `Dashboard.svelte` to use the new store.
5. **Clean Up Navigation**: Remove the "Sets" link from `Sidebar.svelte` and `App.svelte`.
6. **Apply Theme**: Use the new blue color when `viewMode === 'sets'`.
