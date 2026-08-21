# Android App Crashes On Startup In 6.21.0

# status: fixed

# reported problem
MuMa Mobile 6.21.0 crashes immediately on startup. Reported 2026-08-21, the same day the release
went out. Debug builds and the whole unit suite were green.

```
java.lang.ClassCastException: com.google.gson.internal.LinkedTreeMap cannot be cast to
    nl.teunschriks.mumamobile.home.HomeCard
    at nl.teunschriks.mumamobile.home.HomeCardAdapter.onBindViewHolder
    at androidx.recyclerview.widget.RecyclerView$Recycler.tryGetViewHolderForPositionByDeadline
    ...
    at android.view.ViewRootImpl.performTraversals
```

# Possible reason
`CardListCache`, added in 6.21.0 for the stale-while-revalidate work, stored the home screen's cards
as a `Snapshot(cards, fetchedAt)` object and read it back with:

```kotlin
private val snapshotType = object : TypeToken<Snapshot>() {}.type
...
gson.fromJson<Snapshot>(stored, snapshotType)
```

The TypeToken names `Snapshot`, but says nothing about the element type of its `cards` field. Gson
therefore had to learn `List<HomeCard>` from that field's generic signature — and the project builds
release with `android.enableR8.fullMode=true`, where R8 strips generic signatures from classes it was
not explicitly told to keep. `-keepattributes Signature` is set, but that preserves signatures on
kept classes; it does not keep `Snapshot` or `HomeCard`.

With the element type gone, Gson filled the list with `LinkedTreeMap`. Kotlin's `List<HomeCard>` is
erased at runtime, so nothing failed at parse time — the cast happened when the adapter drew the
first cached card, on the first frame of the home screen. Hence a crash on startup, only for a user
whose cache had been written at least once, and only in a release build.

`RecentActivityStore` has stored `HomeCard`s in the same preferences file for many releases without
this. The difference is that it deserializes through `object : TypeToken<MutableList<HomeCard>>() {}`
— the element type travels in the deserializer call, where R8 cannot shrink it away.

The same class of failure is already documented one file over: `proguard-main.pro` carries a note
about R8 full mode breaking Guava's `TypeToken` for exactly the same reason.

**Why nothing caught it.** The unit suite runs unminified, so Gson always had the signature. Nothing
in the pipeline runs the release APK; `muma-mobile:build-release` builds it and does not start it.
There are no on-device tests at all.

# solution
Three layers, smallest first:

1. **`CardListCache` no longer depends on a field signature.** It stores the card list itself and
   reads it through an explicit `TypeToken<MutableList<HomeCard>>`, exactly as `RecentActivityStore`
   does, with the fetch time in a sibling preference key.
2. **An entry it cannot turn into real cards reads as a miss.** That covers the entries 6.21.0
   already wrote — the format differs, so parsing throws and the cache self-heals on the next load —
   and guards against this returning in another shape.
3. **Keep rules for the Gson models** in `proguard-main.pro`: `HomeCard`, `HomeCardType` and
   `TileInfo`. `CardListCache` no longer needs them, but every other stored model still learns its
   shape by reflection, and the next one added will too.

Covered by `CardListCacheTest`, including a test that feeds it a 6.21.0-format entry and requires a
miss.

**Not covered, and this is the real gap:** nothing verifies a *release* build at runtime. A test
that would have caught this has to run the minified APK. First steps towards that are agreed as
follow-up work.
