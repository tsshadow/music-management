package nl.teunschriks.mumamobile.di

import nl.teunschriks.mumamobile.service.ExternalStorageMonitor
import nl.teunschriks.mumamobile.service.MediaPlayerLifecycleSupport
import nl.teunschriks.mumamobile.service.MediaPlayerManager
import nl.teunschriks.mumamobile.service.PlaybackStateSerializer
import nl.teunschriks.mumamobile.subsonic.NetworkAndStorageChecker
import org.koin.dsl.module

/**
 * This Koin module contains the registration of classes related to the media player
 *
 * Everything here is application-scoped. The player used to live in `scope<NavigationActivity>`,
 * which made it unreachable from anything Koin resolves through the root scope: a plain `Fragment`,
 * a `BroadcastReceiver`, a root `single`. Because Koin resolves `by inject()` lazily, that never
 * failed at construction -- it threw `NoDefinitionFoundException` at the first use, often inside a
 * `runCatching` or a `try`, so the app either vanished or silently did nothing. It cost two
 * releases (see `docs/bug-reports/031-app-crashes-on-launch-while-connected-to-the-car.md`).
 *
 * The player never needed the activity: neither constructor takes an `Activity` or a `Context`, and
 * every context they use is `UApp.applicationContext()`. It also outlives the activity in practice,
 * since `PlaybackService` keeps playing while `NavigationActivity` is being recreated. Owning that
 * lifetime here removes the whole class of bug and is the prerequisite for a UI-free native layer
 * (see `docs/designs/universal-ui/technical.md`, Path A phase 1), where a Capacitor
 * `BridgeActivity` replaces `NavigationActivity` altogether.
 *
 * `ScopeFragment`s keep working unchanged: a Koin scope links to the root scope, so a `scoped`
 * lookup falls through to these `single`s.
 */
val mediaPlayerModule = module {

    // These are dependency-free
    single { PlaybackStateSerializer() }
    single { ExternalStorageMonitor() }
    single { NetworkAndStorageChecker() }

    single { MediaPlayerManager(get(), get()) }
    single { MediaPlayerLifecycleSupport(get(), get(), get(), get()) }
}
