# App Crashes On Launch While Connected To The Car

# status: fixed

# reported problem
Opening MuMa Mobile while sitting in the car makes the app disappear. Reported 2026-08-22. The
same build opens normally as soon as the car connection is gone, and the Android Auto screen on the
head unit keeps working throughout. No logs were available: crash detection is off by default.

```
org.koin.core.error.NoDefinitionFoundException:
    No definition found for type 'nl.teunschriks.mumamobile.service.MediaPlayerManager'
```

# Possible reason
Car mode's session object was registered as a root `single` that reached into an activity-scoped
dependency:

```kotlin
single { CarModeSession(isPlaying = { get<MediaPlayerManager>().isPlaying }) }
```

`MediaPlayerManager` is declared `scoped { }` inside `scope<NavigationActivity>` in
`MediaPlayerModule.kt`. A `single` is always resolved by Koin's root scope no matter who asks for
it — `NavigationActivity` is a `ScopeActivity`, but its scope has no definition for
`CarModeSession`, so the lookup falls through to the root scope and the definition lambda runs
there. The root scope cannot see into an activity scope, so the `get` had nowhere to find the
player.

What made it look like a car problem rather than a startup problem is that the lambda is lazy. It
is only invoked on one line — `shouldRaise = isPlaying()` in `CarModeSession.onPresenceChanged` —
and that line is reached only when presence flips to *true*. Without a car, `watchCarPresence`
collects `false`, takes the `Nothing` branch and never calls it, so the app is completely healthy.
With a car already connected at launch, presence is true within the first frames, the collector
asks for an intent, and the exception is thrown on the main thread with nothing catching it.

Android Auto is untouched by this: the head unit is served by `MediaLibraryService`, a separate
entry point that never resolves `CarModeSession`. Which is exactly why the car screen kept working
while the phone app died — and why it read as a car mode fault rather than a wiring fault.

This is the second time this scope has cost a release. `MumaVoiceFragment` was written as a plain
`Fragment`, which also injects from the root scope, and also died only once it touched the player
(fixed in MR !345). The shape is the same both times: code that compiles, starts and navigates, and
fails at the first *use* of a lazily resolved player.

**Why nothing caught it.** `CarModeSessionTest` constructs `CarModeSession` directly and passes its
own lambda, so it exercises the logic and never the wiring. Nothing in the suite resolved anything
out of the real Koin modules, so no test could observe which scope a definition lands in.

# solution
`CarModeSession` no longer has a dependency to resolve. Whether something is playing is passed to
`onPresenceChanged` by the caller:

```kotlin
carModeSession.onPresenceChanged(inCar) { mediaPlayerManager.isPlaying }
```

`NavigationActivity` already holds `MediaPlayerManager` from its own scope, so it is the one place
that can supply it. The class keeps its lambda so the player is still only touched on the branch
that offers the screen, and it stays plain Kotlin for the tests. The definition becomes
`single { CarModeSession() }`, which has nothing left to resolve — the compiler now rules out the
whole failure rather than a review catching it.

Covered by `CarModeSessionWiringTest`, which starts Koin with the real `appPermanentStorage` module,
resolves `CarModeSession` from the root scope and answers a first car connection. It fails with
`NoDefinitionFoundException` against the old wiring. Only that one definition is instantiated, so
the rest of the module — which does need an Android context — stays out of it. `CarModeSessionTest`
also pins that the offer branch is the only one that asks whether anything is playing.

**Adjacent, not changed here:** the `if (dismissed) return CarModeIntent.Nothing` guard in
`onPresenceChanged` is currently unreachable. Reaching it needs a `true` presence while `dismissed`
is set, but the only path back to `true` runs through the `!inCar` branch, which resets `dismissed`
to false. Dismissal still holds for the trip, because a repeated `true` is stopped one line earlier
by the `inCar == present` guard. Worth a look on its own; it is not part of this crash.
