# Configurable Home Screen — Technical Design

> Implements [`functional.md`](functional.md). Phone only; the web dashboard is untouched and does
> not read any of this.

## What replaces what

The home screen had **four** section slots, declared in `res/layout/primary.xml` as four
`<include>`s and paired with the view model's sections **by index** in `MainFragment.render()`. That
is why adding the two feeds in 6.34.0 removed the two recent lists instead of joining them: the
feeds took slots three and four, and those slots' "Meer" actions still pointed at the recent lists.

`primary.xml` now holds one empty `LinearLayout` (`@id/home_sections`) and `MainFragment` inflates
one `home_section` into it per slot the view model asks for. Slots are rebuilt only when their
*shape* changes — the list of `(section, style)` pairs — because that only happens when a setting
does, and rebuilding on every emission would drop the scroll position and restart every image load.

## Data model

| Type | Holds |
|---|---|
| `HomeSectionId` | The seven sections. **Declaration order is screen order**; there is no stored ordering. Each carries its title, the modes it offers, its count steps and its defaults. |
| `HomeSectionMode` | `BUTTON`, `OVERVIEW`, `OFF`. |
| `HomeSectionConfig` | One section's resolved mode and count. |
| `HomeSlot` | One row of the screen: `id` (null for the shared grid), `style`, `state`. |

`HomeCard` gains `source: HomeSectionId?` and **`key` includes it**. Without that, the same album
contributed by Favorieten and by Shortcuts is one identity, and `DiffUtil` drops one of the two
buttons. Outside the grid `source` is null and `key` is exactly what it was.

`HomeCardType` gains `SECTION`: a button standing for a whole destination, whose `itemId` is a
`HomeSectionId` name. `HomeCardNavigator.directionsForSection` resolves it; an unknown id falls back
to the library rather than crashing a screen that is otherwise fine.

## Settings

One `ListPreference` per section under a new **Startscherm** category, plus a count where the
section takes one. Keys are `homeMode<SECTION>` and `homeCount<SECTION>`, values the
`HomeSectionMode` names.

`HomeLayout.resolve()` is pure — it takes the stored values as functions — so every rule about what
an upgrading listener gets is testable without an Android context. `HomeLayoutSettings` is the thin
part that reads the real preferences, per load rather than cached, which is what lets a change take
effect on the next return to the home screen.

Resolution rules, all covered by `HomeLayoutTest`:

- A mode the section does not offer, or a string that is not a mode, resolves to the section's
  default. A preferences file can be ahead of or behind the app; neither is worth a crash.
- `memories_on_home = false` means `MEMORIES` is `OFF`, unless an explicit mode says otherwise.
- `home_shortcut_count` and `home_list_count` are still the counts for the shortcuts and the two
  recent lists. Nothing about how much they show changes on upgrade.
- A count is pulled into range but **not** onto a step: an existing 7 stays 7. The steps are what
  the settings screen offers, not a claim that nothing else renders.

The setup wizard's memories step writes `homeModeMEMORIES` now instead of the old checkbox.
`WizardCatalogTest` asserts every key the wizard writes exists on the settings screen, which is what
caught the change.

## Loading

`HomeViewModel` reads the configuration, then emits slots **before** loading anything:

- Sections that stand for one destination (both feeds, both recent lists, Memories) contribute their
  button with no request at all, so the grid is on screen immediately.
- Shortcuts come from `RecentActivityStore`, which is local.
- Favorieten is the only button that needs a request; its part of the grid fills in behind the rest.
- Memories' button is up immediately and gains its "Vandaag, 1 jaar geleden · 30 nummers" subtitle
  when the request returns.

Each section's contribution is kept separately (`buttonCards`, a `ConcurrentHashMap`) and the grid is
recomposed from it, so a section that answers late or fails does not clear the others. A failed
button load keeps whatever that section contributed last: unlike a list there is nothing partial to
show, and an entry vanishing reads as the section being gone rather than as a request that failed.

Overviews keep the existing path unchanged — cache first as `Stale`, then `Content`, `Empty` on a
confirmed empty answer, and cached-cards-on-failure.

Providers handed in by a test still decide the whole screen: one overview slot each, in order, and
no grid. That is what keeps `HomeViewModelTest` about loading behaviour rather than about settings.

## The feed page on the phone

`trackCollectionFragment` gains a `feed` argument and `TrackCollectionModel.LoadParams` a
`feedSlug`. Set, it is the whole query: the list is MuMa's ranking, so no filters are applied on top
of it, it is not sortable, and `hasMoreData` is false — every other list here is a query this screen
can ask for more of, and a feed is a fixed set that was already ordered when it arrived.

Tracks come from the shared `FeedRepository` (the Koin `single`), so opening the page costs nothing
when the car or the home screen already fetched today's feed.

## Cross-App Impact

None. The web dashboard has its own home screen and does not read these preferences;
`services/music_manager` is untouched. Nothing is synced between devices — the phone's settings-sync
hook is empty today, and this does not change that.

## Technical Acceptance Criteria

1. `HomeLayout.resolve` returns one config per `HomeSectionId`, in declaration order, for any input.
2. An unparseable or unsupported stored mode resolves to the section's default, never to a mode the
   section does not offer.
3. `home_shortcut_count = 7` resolves to 7, and `homeCountDAILY_MIX = 400` resolves to 10.
4. `HomeCard.key` differs for the same album contributed by two sections, and is unchanged for a
   card with no source.
5. `HomeButtons.grid` orders by `HomeSectionId` declaration order whatever order the map is in, and
   keeps one section's buttons adjacent.
6. `MainFragment` rebuilds its slots only when the shape changes.
7. A `SECTION` card resolves to its own section's destination; an unknown id resolves to the library.
8. A feed page applies no filters, is not sortable and does not page.
9. The wizard's memories step writes a key that exists on the settings screen.
10. Existing `HomeViewModelTest` behaviour — loading, empty, failure, cache — is unchanged.
