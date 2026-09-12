package nl.teunschriks.mumamobile.service

import io.reactivex.rxjava3.android.schedulers.AndroidSchedulers
import io.reactivex.rxjava3.core.Observable
import io.reactivex.rxjava3.core.Scheduler
import io.reactivex.rxjava3.disposables.CompositeDisposable
import io.reactivex.rxjava3.disposables.Disposable
import io.reactivex.rxjava3.subjects.PublishSubject
import java.util.concurrent.TimeUnit
import nl.teunschriks.mumamobile.data.RatingUpdate
import nl.teunschriks.mumamobile.data.ServerSetting
import nl.teunschriks.mumamobile.domain.Track

class RxBus {

    /**
     * IMPORTANT: methods like .delay() or .throttle() will implicitly change the thread to the
     * RxComputationScheduler. Always use the function call with the additional arguments of the
     * desired scheduler
     **/
    companion object {

        fun mainThread(): Scheduler = AndroidSchedulers.mainThread()

        val shufflePlayPublisher: PublishSubject<Boolean> =
            PublishSubject.create()
        val shufflePlayObservable: Observable<Boolean> =
            shufflePlayPublisher

        var activeServerChangingPublisher: PublishSubject<Int> =
            PublishSubject.create()

        // Subscribers should be called on the UI thread
        var activeServerChangingObservable: Observable<Int> =
            activeServerChangingPublisher.observeOn(mainThread())

        var activeServerChangedPublisher: PublishSubject<ServerSetting> =
            PublishSubject.create()
        var activeServerChangedObservable: Observable<ServerSetting> =
            activeServerChangedPublisher.observeOn(mainThread())

        // Fired after credentials were accepted at the login screen. Logging back in on the same
        // server does not change the active server, so activeServerChanged says nothing here, yet
        // screens that gave up while logged out still need to fetch their content.
        val loginSucceededPublisher: PublishSubject<Unit> =
            PublishSubject.create()
        val loginSucceededObservable: Observable<Unit> =
            loginSucceededPublisher.observeOn(mainThread())

        // Fired when the server rejected the credentials the app is logged in with.
        // Several requests usually fail at once, and each one reports separately, so this is
        // throttled: the session only needs to be torn down once.
        val authenticationFailurePublisher: PublishSubject<Unit> =
            PublishSubject.create()
        val authenticationFailureObservable: Observable<Unit> =
            authenticationFailurePublisher
                // Need to specify thread, see comment at beginning
                .throttleFirst(AUTH_FAILURE_THROTTLE_SECONDS, TimeUnit.SECONDS, mainThread())
                .observeOn(mainThread())

        val themeChangedEventPublisher: PublishSubject<Unit> =
            PublishSubject.create()
        val themeChangedEventObservable: Observable<Unit> =
            themeChangedEventPublisher.observeOn(mainThread())

        val setsModeChangedPublisher: PublishSubject<Boolean> =
            PublishSubject.create()
        val setsModeChangedObservable: Observable<Boolean> =
            setsModeChangedPublisher.observeOn(mainThread())

        val musicFolderChangedEventPublisher: PublishSubject<Folder> =
            PublishSubject.create()
        val musicFolderChangedEventObservable: Observable<Folder> =
            musicFolderChangedEventPublisher.observeOn(mainThread())

        val playerStatePublisher: PublishSubject<StateWithTrack> =
            PublishSubject.create()
        val playerStateObservable: Observable<StateWithTrack> =
            playerStatePublisher
                .replay(1)
                .autoConnect(0)
        val throttledPlayerStateObservable: Observable<StateWithTrack> =
            playerStatePublisher
                .replay(1)
                .autoConnect(0)
                // Need to specify thread, see comment at beginning
                .throttleLatest(300, TimeUnit.MILLISECONDS, mainThread())

        // A failed item leaves Media3 in STATE_IDLE, which is indistinguishable from "nothing
        // loaded". Without this the Capacitor shell could only report the silence, never the
        // reason for it.
        val playerErrorPublisher: PublishSubject<PlayerError> =
            PublishSubject.create()
        val playerErrorObservable: Observable<PlayerError> =
            playerErrorPublisher.observeOn(mainThread())

        val playlistPublisher: PublishSubject<List<Track>> =
            PublishSubject.create()
        val playlistObservable: Observable<List<Track>> =
            playlistPublisher
                .replay(1)
                .autoConnect(0)
        val throttledPlaylistObservable: Observable<List<Track>> =
            playlistPublisher
                .replay(1)
                .autoConnect(0)
                // Need to specify thread, see comment at beginning
                .throttleLatest(300, TimeUnit.MILLISECONDS, mainThread())

        val trackDownloadStatePublisher: PublishSubject<TrackDownloadState> =
            PublishSubject.create()
        val trackDownloadStateObservable: Observable<TrackDownloadState> =
            trackDownloadStatePublisher.observeOn(mainThread())

        // Sends a RatingUpdate which was just triggered by the user
        val ratingSubmitter: PublishSubject<RatingUpdate> =
            PublishSubject.create()
        val ratingSubmitterObservable: Observable<RatingUpdate> =
            ratingSubmitter

        // Sends a RatingUpdate which was successfully submitted to the server or database
        val ratingPublished: PublishSubject<RatingUpdate> =
            PublishSubject.create()
        val ratingPublishedObservable: Observable<RatingUpdate> =
            ratingPublished

        // Commands
        val dismissNowPlayingCommandPublisher: PublishSubject<Unit> =
            PublishSubject.create()
        val dismissNowPlayingCommandObservable: Observable<Unit> =
            dismissNowPlayingCommandPublisher.observeOn(mainThread())

        val createServiceCommandPublisher: PublishSubject<Unit> =
            PublishSubject.create()
        val createServiceCommandObservable: Observable<Unit> =
            createServiceCommandPublisher.observeOn(mainThread())

        val stopServiceCommandPublisher: PublishSubject<Unit> =
            PublishSubject.create()
        val stopServiceCommandObservable: Observable<Unit> =
            stopServiceCommandPublisher.observeOn(mainThread())

        val shutdownCommandPublisher: PublishSubject<Unit> =
            PublishSubject.create()
        val shutdownCommandObservable: Observable<Unit> =
            shutdownCommandPublisher.observeOn(mainThread())

        private const val AUTH_FAILURE_THROTTLE_SECONDS = 5L
    }

    data class StateWithTrack(
        val track: Track?,
        val index: Int = -1,
        val isPlaying: Boolean = false,
        val state: Int
    )

    data class TrackDownloadState(val id: String, val state: DownloadState, val progress: Int?)

    /** What Media3 reported when an item refused to play. [code] is a `PlaybackException` code. */
    data class PlayerError(val code: Int, val message: String?)

    data class Folder(val id: String?)
}

operator fun CompositeDisposable.plusAssign(disposable: Disposable) {
    this.add(disposable)
}
