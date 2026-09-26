<script>
  import { t } from './i18n/index.js';
  import { onMount } from 'svelte';
  import { currentTrack, playerState, authParams, credentials, playlist, isMobile, syncMode, highlightedTrackId, activeView, radioChannel, radioNowPlaying, mumaApiUrl, mumaApiKey, equalizerSettings, restUrl, nowPlayingOpen, openNowPlaying, closeNowPlaying, flushPersistedStores } from './store.js';
  import Equalizer from './Equalizer.svelte';
  import NowPlaying from './NowPlaying.svelte';
  import { fetchLyricsLines } from './lyrics.js';
  import * as equalizer from './equalizer.js';
  // Everything this component does with playback goes through here; the engine
  // behind it is the browser's <audio> today and the phone's PlaybackService
  // later. See platform/index.js for the interface and
  // docs/designs/universal-ui/ for why.
  import { platform } from './platform/index.js';
  import { logAction } from './diagnosticsLog.js';
  import { createNativeQueue, trackAfterCommand } from './nativeQueue.js';
  import { createRadioController } from './radioController.js';
  import { createRadioStartGuard } from './radioStartGuard.js';
  import { shouldPushJamState } from './radioSync.js';
  import { resolveDuration, progressPercent, formatTime, formatClock } from './playerProgress.js';
  import { describeFilter } from './management/radioChannels.js';
  import { snapshotOf, restoreTarget, bulletinStreamUrl } from './newsQueue.js';
  import { startQueue } from './queue.js';
  import { startTrail, stepBack, stepForward } from './shuffleHistory.js';
  import { releaseDateLabel } from './trackDate.js';
  import { isSet } from './downloads.js';
  import {
    resumeKeyFor,
    shouldResume,
    loadSetResumePositions,
    saveSetResumePosition,
  } from './setResume.js';
  import ArtistList from './ArtistList.svelte';
  import Artwork from './Artwork.svelte';
  import { getArtistImageUrl, primaryArtistOf, subsonicError } from './utils.js';
  import { getHeaders } from './mumaApi.js';
  import { notify } from './notifications.js';
  import { ratings, ratingOf as ratingFor, tapStar } from './ratings.js';
  import { artistImageFallback, coverArtSrc, FALLBACK, localCoverArt, resolveCoverArt } from './coverArt.js';
  import { offline, subsonicPost } from './subsonic.js';
  import { fetchGenreTints, trackTint } from './genreTints.js';

  const { onnavigate, ontoggleQueue } = $props();

  // `$state` rather than a plain `let`: the element is inside an `{#if}` now
  // (there is none in the shell), so the binding writes to it after the first
  // render and Svelte refuses a non-reactive target for that.
  let audioElement = $state(null);
  // Effects declared here run before onMount, so the engine has nothing to play
  // through yet when the first of them fires. Anything that needs a live engine
  // waits for this.
  let engineReady = $state(false);

  // Whether the platform service holds the queue instead of this component.
  // True inside the Android shell and false in a browser; every place below
  // that behaves differently branches on this and nothing else. See
  // platform/index.js (`ownsQueue`) and nativeQueue.js.
  const nativePlayback = platform.player.ownsQueue;
  /** @type {ReturnType<typeof createNativeQueue>|null} */
  let nativeQueue = null;
  // Bumped whenever an `adopt()`/`sync()` on `nativeQueue` settles, so `queueIndex` below --
  // a plain function call into a variable Svelte's reactivity does not see on its own --
  // recomputes after the native side's position actually changes rather than only when
  // `$playlist` or `$currentTrack` do (see `queueIndex`'s own comment).
  let nativeQueuePositionTick = $state(0);
  let muted = $state(false);
  let lastVolume = $state(50);
  let lastSyncTime = null;
  let lastPushTime = 0;
  let isSyncing = false;

  let radioController = null;
  // One guard for "the listener asked for a channel" (drops a repeat tap while the service is
  // still tuning in) and one for the display controller's own asynchronous start; see
  // `radioStartGuard.js`.
  const radioStartGuard = createRadioStartGuard();
  const radioDisplayGuard = createRadioStartGuard();
  let radioTickInterval = null;
  let radioRefreshInterval = null;
  let radioClockInterval = null;
  let radioChannels = $state([]);
  // Set while a news bulletin is interrupting the music, and holding what to
  // put back when it ends.
  let newsSnapshot = $state(null);
  let newsObjectUrl = null;
  let showRadioPicker = $state(false);

  let showEqualizer = $state(false);
  let equalizerPanelEl = $state(null);
  const equalizerSupported = equalizer.isSupported();

  // Genre tints for the artwork panel and the full player's background
  // gradient (see `trackTint` in genreTints.js). Fetched once here rather
  // than by `NowPlaying` itself, the same reasoning as `lyricsLines` below --
  // one fetch, two renderings (mini player background is untinted, the
  // full-screen one is not).
  let genreTints = $state({});
  onMount(() => {
    fetchGenreTints().then((t) => (genreTints = t));
  });

  // The output the phone plays through, for the label on the full-screen player (increment H,
  // technical.md). Native only: a browser answers null and never fires the event, and null is
  // what hides the label. Read once on mount rather than waited for, since the event only
  // reaches a subscriber that was already listening when the headset connected; then kept
  // current by the subscription until this component goes away.
  let outputRoute = $state(null);
  onMount(() => {
    if (!platform.system.isNative) return;
    platform.system.outputRoute().then((route) => (outputRoute = route));
    return platform.system.onOutputRouteChanged((route) => (outputRoute = route));
  });

  /**
   * A rejection here means neither the system output switcher nor the Bluetooth settings screen
   * exists on this build -- nothing the player can do about it, so it is logged rather than
   * surfaced, and never left as an unhandled rejection from a click handler.
   */
  function openOutputPicker() {
    platform.system
      .openOutputPicker()
      .catch((error) => console.warn('Could not open the output picker', error));
  }

  // The current track's lyrics, or an empty array once LMS has answered and
  // found none -- most tracks. Computed here rather than inside `NowPlaying`
  // (or a second copy on the desktop panel below) for the same reason
  // `currentRating` already is: one fetch, two renderings of the same state.
  // An empty array is also what hides the affordance in both places, so
  // nothing shows a "no lyrics" placeholder for the common case.
  let lyricsLines = $state([]);
  let showLyricsPanel = $state(false);

  /**
   * Closes the panel on a click elsewhere.
   *
   * Every toggle button has to be excluded as well as the panel, not just one
   * of them: on mobile the button sits in the mini player and the sheet is a
   * separate fixed element, and Now Playing renders a third button of its own
   * -- without this check any of their own clicks would close the sheet again
   * the instant its handler opened it. `data-eq-toggle` is what all three
   * share, rather than a separate bound element ref per button.
   */
  function closeEqualizerOnOutsideClick(event) {
    if (equalizerPanelEl?.contains(event.target)) return;
    if (event.target.closest('[data-eq-toggle]')) return;
    showEqualizer = false;
  }

  $effect(() => {
    if (!showEqualizer) return;
    window.addEventListener('click', closeEqualizerOnOutsideClick);
    return () => window.removeEventListener('click', closeEqualizerOnOutsideClick);
  });

  $effect(() => {
    const id = track?.id;
    let cancelled = false;
    lyricsLines = [];
    showLyricsPanel = false;
    if (id) {
      fetchLyricsLines(id).then((lines) => {
        if (!cancelled) lyricsLines = lines;
      });
    }
    return () => {
      cancelled = true;
    };
  });

  // Settings reach the audio graph through the engine, which owns the element
  // they have to be built around -- so this waits until it has one.
  $effect(() => {
    const settings = $equalizerSettings;
    if (engineReady) platform.player.setEqualizer(settings);
  });

  /**
   * Builds a stream URL for radio playback. `format=mp3` is required: LMS only
   * honours `timeOffset` on the transcoding path (MediaRetrieval.cpp:146-147).
   *
   * @param {string} trackId
   * @param {number} offsetSeconds
   * @returns {string}
   */
  function radioStreamUrl(trackId, offsetSeconds) {
    return restUrl(`/rest/stream?id=${trackId}&format=mp3&maxBitRate=320&timeOffset=${offsetSeconds}&${$authParams}`);
  }

  /**
   * A sentinel `newsSnapshot`, used only on a native shell.
   *
   * On the browser `newsSnapshot` is what to restore when the bulletin ends -- the interrupted
   * track or channel, and the position. On native there is nothing here to restore: the service
   * does that itself, entirely on the far side
   * (`NewsPlaybackController.stopAndRestore`/`NewsQueueRules.kt`, the mirror of `newsQueue.js`).
   * `newsSnapshot` is kept truthy anyway, because every other place in this component -- the
   * colour of the news button, `currentLength()`'s length fallback, `handleEnded()` -- only ever
   * asks whether it is set, never what is in it.
   */
  const NATIVE_NEWS_MARKER = Object.freeze({ native: true });

  /**
   * Starts (or restarts) the display-only poll of `/api/radio/{slug}/state`.
   *
   * Every caller below wants the same three things: the store updated, `radioController` pointed
   * at the right channel, and a ten-second refresh loop feeding `radioNowPlaying`. What differs is
   * whether the service still needs to be told to tune in -- `startRadio` (a listener tapped a
   * channel) does, `reconcileNativeRadioNews` (the service is already doing it, from Android Auto,
   * Assistant, or a WebView recreated mid-channel) must not, or it would restart the stream for no
   * reason.
   *
   * @param {string} slug
   */
  function beginRadioDisplay(slug) {
    // A controller from an earlier start may still be measuring the clock or fetching its first
    // state; retire it so it cannot load its stream into the element after this one does.
    radioController?.retire();
    const ticket = radioDisplayGuard.begin();
    clearInterval(radioTickInterval);
    clearInterval(radioRefreshInterval);
    clearInterval(radioClockInterval);
    radioTickInterval = null;
    radioClockInterval = null;

    radioController = createRadioController({
      // Native: no element to drive, and none of its own maths to run -- the
      // service corrects its own drift. This instance exists only for
      // `getEntry()`. See the `audio` note on `createRadioController`.
      audio: nativePlayback ? null : platform.player.element(),
      apiBase: $mumaApiUrl,
      apiKey: $mumaApiKey,
      streamUrlFor: radioStreamUrl,
    });
    radioChannel.set(slug);
    radioController
      .start(slug)
      .then(() => {
        if (ticket?.isCurrent()) radioNowPlaying.set(radioController?.getEntry() ?? null);
      })
      .catch((e) => {
        console.error($t('radio.couldNotStart'), e);
        // A newer start (or a stop) has happened since: its state is not ours to tear down.
        if (!ticket?.isCurrent()) return;
        // The service (native) or the element (browser) never actually joined
        // the channel; showing radio as on with nothing playing and no
        // now-playing metadata would be a stuck picker rather than an error.
        endRadioDisplay();
      });

    radioRefreshInterval = setInterval(async () => {
      await radioController?.refresh();
      radioNowPlaying.set(radioController?.getEntry() ?? null);
    }, 10000);
    if (!nativePlayback) {
      radioTickInterval = setInterval(() => radioController?.tick(), 2000);
      // Clocks drift over a long listening session, so re-measure now and then.
      radioClockInterval = setInterval(() => radioController?.measureClockOffset(), 300000);
    }
  }

  /** Tears down the display poll and the local radio state, without touching the service. */
  function endRadioDisplay() {
    radioDisplayGuard.invalidate();
    radioController?.retire();
    clearInterval(radioTickInterval);
    clearInterval(radioRefreshInterval);
    clearInterval(radioClockInterval);
    radioTickInterval = null;
    radioRefreshInterval = null;
    radioClockInterval = null;
    radioController = null;
    radioChannel.set(null);
    radioNowPlaying.set(null);
  }

  /**
   * Notices radio or a bulletin that this component did not start itself -- Android Auto,
   * Assistant, a car button, or a WebView recreated mid-channel or mid-bulletin. Native only; a
   * browser tab is always the one deciding either, and `state()` never carries these two fields
   * there.
   *
   * Called from every place this component already reads a fresh native snapshot: on mount, and
   * on every `timeupdate` while something plays.
   *
   * @param {object} state - `platform.player.state()`.
   */
  function reconcileNativeRadioNews(state) {
    if (!nativePlayback) return;

    const slug = state.radioChannel ?? null;
    if (slug && slug !== $radioChannel) {
      beginRadioDisplay(slug);
    } else if (!slug && $radioChannel) {
      endRadioDisplay();
      showRadioPicker = false;
    }

    const active = state.newsPlaying === true;
    if (active !== Boolean(newsSnapshot)) {
      newsSnapshot = active ? NATIVE_NEWS_MARKER : null;
    }
  }

  /**
   * Switches radio off, or offers the channels on air. With one channel there is
   * nothing to choose, so it starts straight away.
   */
  async function toggleRadio() {
    if ($radioChannel) {
      radioStartGuard.invalidate();
      if (nativePlayback) {
        // Radio is driven entirely by the service; leaving it is a session
        // command rather than anything this controller does. `pause()`
        // afterwards is what makes it go silent instead of carrying straight on
        // into whatever queue item comes back -- the same thing
        // `radioController.stop()`'s own `audio.pause()` does for the browser.
        try {
          await platform.player.stopRadio();
          platform.player.pause();
        } catch (e) {
          console.error($t('radio.couldNotStart'), e);
        }
      } else {
        radioController?.stop();
      }
      endRadioDisplay();
      showRadioPicker = false;
      return;
    }

    if (showRadioPicker) {
      showRadioPicker = false;
      return;
    }

    try {
      const response = await fetch(`${$mumaApiUrl}/api/radio/channels`, {
        headers: { 'X-API-Key': $mumaApiKey },
      });
      const body = await response.json();
      radioChannels = body.channels || [];
      if (!radioChannels.length) {
        console.warn($t('radio.noChannels'));
        return;
      }
      if (radioChannels.length === 1) {
        await startRadio(radioChannels[0]);
        return;
      }
      showRadioPicker = true;
    } catch (e) {
      console.error($t('radio.couldNotStart'), e);
    }
  }

  /**
   * Tunes into one channel. Requires a user gesture, which is exactly why this
   * runs from a click handler: starting playback from a timer would be blocked
   * by browser autoplay policy.
   *
   * @param {{slug: string}} channel
   */
  async function startRadio(channel) {
    showRadioPicker = false;
    // A second tap on the channel that is still starting is the same request, not a new one.
    const ticket = radioStartGuard.begin(channel.slug);
    if (!ticket) return;
    try {
      if (nativePlayback) {
        // The service streams the channel and locks onto the server's timeline
        // itself -- the same maths as `radioSync.js`, reused from Android
        // Auto's own radio support (`RadioPlaybackController.kt`) rather than a
        // third copy of it. `beginRadioDisplay` below only keeps a display
        // poller of its own for the mini player and Now Playing.
        await platform.player.startRadio(channel.slug);
        // Another channel was picked, or radio switched off, while the service was tuning in:
        // that later action owns the display now.
        if (!ticket.isCurrent()) return;
      }
      beginRadioDisplay(channel.slug);
    } catch (e) {
      console.error($t('radio.couldNotStart'), e);
    } finally {
      ticket.done();
    }
  }

  /**
   * Plays the most recent bulletin, or gives the music back if one is running.
   *
   * The audio element cannot send an `X-API-Key` header, and the endpoint takes
   * the key no other way, so the bulletin is fetched and played from a blob.
   * A ten-minute recording is around 14 MB, which is a short wait on a LAN and
   * buys the same authentication the rest of the app uses.
   */
  async function toggleNews() {
    if (nativePlayback) {
      // One call either way: the service already knows whether a bulletin is
      // running, so this is the exact toggle the notification's own news
      // button performs. It also snapshots and restores the interrupted queue
      // (and re-tunes radio, if that was on) entirely on its own --
      // `NewsPlaybackController.kt` is the mirror of the browser logic below.
      try {
        await platform.player.toggleNews();
        newsSnapshot = newsSnapshot ? null : NATIVE_NEWS_MARKER;
      } catch (e) {
        console.error('Could not toggle the news', e);
        notify.error($t('news.couldNotPlay'), { detail: e.message });
      }
      return;
    }
    if (newsSnapshot) {
      await stopNews();
      return;
    }
    try {
      const headers = getHeaders();
      const response = await fetch(`${$mumaApiUrl}/api/news/bulletins/latest`, { headers });
      // Only a 404 means what the message says. Every other status is the hop
      // failing -- an expired key, the proxy's concurrency gate, a bulletin too
      // large for it -- and calling that "nothing recorded yet" sent every reader
      // looking at the recorder, which was working the whole time.
      if (!response.ok) {
        if (response.status === 404) notify.error($t('news.none'));
        else notify.error($t('news.couldNotPlay'), { detail: `HTTP ${response.status}` });
        return;
      }
      const bulletin = await response.json();
      const audioResponse = await fetch(bulletinStreamUrl($mumaApiUrl, bulletin.id), { headers });
      if (!audioResponse.ok) {
        notify.error($t('news.couldNotPlay'), { detail: `HTTP ${audioResponse.status}` });
        return;
      }
      const blob = await audioResponse.blob();

      newsSnapshot = snapshotOf({
        trackId: $radioChannel ? null : (track?.id ?? null),
        positionSeconds: platform.player.state().position,
        radioChannel: $radioChannel,
      });
      // Radio has to be switched off rather than paused: it drives the same
      // element, and it would keep correcting the bulletin's position.
      if ($radioChannel) await toggleRadio();

      newsObjectUrl = URL.createObjectURL(blob);
      await platform.player.load({ url: newsObjectUrl, trackId: null, autoplay: true });
    } catch (e) {
      console.error('Could not play the news', e);
      notify.error($t('news.couldNotPlay'), { detail: e.message });
    }
  }

  /** Ends the bulletin and resumes whatever it interrupted. */
  async function stopNews() {
    const target = restoreTarget(newsSnapshot);
    newsSnapshot = null;
    if (newsObjectUrl) {
      URL.revokeObjectURL(newsObjectUrl);
      newsObjectUrl = null;
    }

    if (target.action === 'retune') {
      await startRadio({ slug: target.channel });
      return;
    }
    if (target.action === 'none') {
      platform.player.stop();
      return;
    }

    try {
      await platform.player.load({
        url: streamUrl,
        trackId: target.trackId,
        position: target.positionSeconds,
        autoplay: true,
      });
    } catch (e) {
      if (e.name !== 'AbortError') console.error('Could not resume after the news', e);
    }
  }

  /**
   * Sends the current player state to the server if sync mode is active.
   * 
   * @param {boolean|null} overridePlaying - Optional override for the playing state.
   * @param {string|null} overrideTrackId - Optional override for the current track ID.
   */
  async function pushJamState(overridePlaying = null, overrideTrackId = null) {
    if ($syncMode === 'off' || isSyncing || !$credentials.username) return;
    lastPushTime = Date.now();
    try {
        // Use overrides if provided, otherwise use local state
        const engine = platform.player.state();
        const currentId = overrideTrackId !== null ? overrideTrackId : ($currentTrack?.id || '');
        const isPlaying = overridePlaying !== null ? overridePlaying : engine.status === 'playing';
        const position = Math.floor(engine.position * 1000);

        // One `id` per queued track: a POST body, because a long queue in the query string
        // is a request line proxies refuse with 414.
        const fields = $playlist.map((t) => ['id', t.id]);
        if (currentId !== '') fields.push(['current', currentId]);
        fields.push(['playing', isPlaying]);
        // In follower mode, we NEVER push periodic position to avoid fighting the host.
        // The 'position' parameter is only included if we are the Host.
        if ($syncMode === 'host') fields.push(['position', position]);

        await subsonicPost('savePlayQueue', fields, $authParams);
    } catch (e) {
        console.error("Jam push failed", e);
    }
  }

  /**
   * Fetches the player state from the server and synchronizes the local player.
   */
  async function syncJam() {
    if ($syncMode === 'off' || isSyncing || !$credentials.username || !platform.player.ready()) return;

    // Don't sync from server if we just pushed our own state (within last 5 seconds)
    // to avoid "jumps" caused by server having slightly outdated state.
    if (Date.now() - lastPushTime < 5000) return;

    isSyncing = true;
    try {
      const params = $authParams;
      const response = await fetch(restUrl(`/rest/getPlayQueue?${params}`));
      const data = await response.json();
      const playQueue = data['subsonic-response']?.playQueue;

      if (playQueue) {
        const serverChanged = playQueue.changed;
        if (serverChanged !== lastSyncTime) {
          if (playQueue.entry) {
            const tracks = Array.isArray(playQueue.entry) ? playQueue.entry : [playQueue.entry];

            // Sync playlist. A jam sync restores a queue, it does not start one -- the
            // 'view: null' here clears queueSource instead of attributing the synced
            // tracks to whatever screen happens to be open on this device right now.
            if (JSON.stringify(tracks.map(t => t.id)) !== JSON.stringify($playlist.map(t => t.id))) {
                startQueue(tracks, { view: null });
            }

            // Sync current track
            const currentTrackId = playQueue.current;
            const serverTrack = tracks.find(t => t.id === currentTrackId);
            const trackChanged = serverTrack && String($currentTrack?.id) !== String(serverTrack.id);

            const serverPlaying = playQueue.playing === "true" || playQueue.playing === true;
            const playingChanged = serverPlaying !== (platform.player.state().status === 'playing');

            // HOST LOGIC: Only apply changes if the server state is different from local
            // (indicating a remote command from a Follower)
            if ($syncMode === 'host') {
                if (trackChanged || playingChanged) {
                    if (trackChanged) currentTrack.set(serverTrack);
                    if (playingChanged) {
                        if (serverPlaying) platform.player.play().catch(() => {});
                        else platform.player.pause();
                    }
                }
                lastSyncTime = serverChanged;
                return;
            }

            // JAM FOLLOWER LOGIC: Remote control, no local audio
            if ($syncMode === 'follower-jam') {
                if (trackChanged) {
                    currentTrack.set(serverTrack);
                }
                // Update local playing state store so UI reflects host state
                playerState.update(s => ({ ...s, playing: serverPlaying }));
                
                // Ensure audio is stopped
                if (platform.player.state().status === 'playing') {
                    platform.player.pause();
                }
                lastSyncTime = serverChanged;
                return;
            }

            // RADIO FOLLOWER LOGIC: Apply everything from server (Listen along)
            if (trackChanged) {
                currentTrack.set(serverTrack);
            }

            const serverPos = (playQueue.position || 0) / 1000;
            const engine = platform.player.state();

            // Sync position if difference > 5 seconds
            if (Math.abs(engine.position - serverPos) > 5) {
                platform.player.seek(serverPos);
            }

            // Sync play/pause
            if (serverPlaying && engine.status !== 'playing') {
                platform.player.play().catch(() => {});
            } else if (!serverPlaying && engine.status === 'playing') {
                platform.player.pause();
            }

            lastSyncTime = serverChanged;
          }
        }
      }
    } catch (e) {
      console.error("Jam sync failed", e);
    } finally {
      isSyncing = false;
    }
  }

  /**
   * Toggles between play and pause states.
   */
  function togglePlay() {
    if (!platform.player.ready()) return;
    logAction(platform.player.state().status === 'playing' ? 'player.pause' : 'player.play', {
      trackId: track?.id ?? null,
    });

    if ($syncMode === 'follower-jam') {
        // Remote control: toggle the state reported by the server
        pushJamState(!$playerState.playing);
        return;
    }

    if (platform.player.state().status === 'playing') {
      platform.player.pause();
    } else {
      platform.player.play().catch(e => {
        console.error("Playback failed", e);
        notify.error($t('notify.playbackFailed'), { detail: e.message });
      });
    }
    if ($syncMode !== 'off') {
      pushJamState();
    }
  }

  // Where shuffle play has been. It is not in `playerState` because nothing outside
  // this component reads it and it must not survive a reload as a list of ids that
  // the restored queue may no longer contain.
  let shuffleTrail = $state(startTrail(null));

  /**
   * The trail to step through, restarted when it has lost touch with the queue.
   *
   * A queue swap or a track picked straight out of the list leaves the trail pointing
   * at something else entirely; carrying on from there would send "previous" to a
   * track the listener never played.
   *
   * @param {Array} queue - The tracks in the queue.
   * @param {string|null} playingId - Id of the track playing now.
   * @returns {{ids: string[], position: number}} The trail to use.
   */
  function trailFor(queue, playingId) {
      const known = new Set(queue.map(track => String(track.id)));
      const onTrack = shuffleTrail.ids[shuffleTrail.position] === playingId;
      const intact = shuffleTrail.ids.every(id => known.has(id));
      return onTrack && intact ? shuffleTrail : startTrail(playingId);
  }

  /**
   * On a native shell, hands a next/previous to the service as an intent and reports whether it
   * did. Bug report 095.
   *
   * The service holds the queue and is the only side that knows which item it is on right now;
   * this component only learns that from a report that is a bridge hop behind. Working out the
   * neighbour here and pushing it as a new queue position meant a second tap, landing before the
   * first move was reported, computed its target from a track the service had already left --
   * and the two sides then kept correcting each other. Asking the service for "next" makes a
   * second tap relative to wherever the first one got to (Media3 masks each call), so N taps move
   * N tracks, shuffle and repeat are the service's own, and the UI follows the reports exactly as
   * it does for the notification or a head unit.
   *
   * Not for a jam follower, whose "next" is a request to the host rather than to this device.
   *
   * @param {'next'|'previous'} direction
   * @returns {boolean} True when the service was asked and the caller has nothing left to do.
   */
  function sendTransportIntent(direction) {
      if (!nativePlayback || $syncMode === 'follower-jam') return false;
      if (direction === 'next') platform.player.next();
      else platform.player.previous();
      return true;
  }

  /**
   * Plays the next track in the playlist.
   * Handles shuffle and repeat logic.
   */
  function playNext() {
      const p = $playlist;
      if (p.length === 0) return;
      logAction('player.next', { trackId: $currentTrack?.id ?? null });
      if (sendTransportIntent('next')) return;
      const currentTrackId = $currentTrack ? String($currentTrack.id) : null;
      const currentIndex = p.findIndex(t => String(t.id) === currentTrackId);

      let nextIndex;
      // Native only: the service has its own shuffle order, and this component never sees it, so
      // walking a JS-decided trail here would disagree with whatever it actually plays next.
      if ($playerState.shuffle && !nativePlayback) {
          // Walk the trail rather than drawing blind, so a previous followed by a
          // next lands back on the track it came from instead of a third one.
          const stepped = stepForward(trailFor(p, currentTrackId), p.map(t => String(t.id)));
          shuffleTrail = stepped.trail;
          nextIndex = p.findIndex(t => String(t.id) === stepped.id);
          if (nextIndex < 0) return;
      } else {
          nextIndex = currentIndex + 1;
          if (nextIndex >= p.length) {
              if ($playerState.repeat === 'all') {
                  nextIndex = 0;
              } else {
                  return;
              }
          }
      }

      const nextTrack = p[nextIndex];
      if (nextTrack) {
          if ($syncMode === 'follower-jam') {
              // Remote control: send intent to play next track
              pushJamState(true, nextTrack.id);
              return;
          }

          // If it's the same track (e.g. single track playlist), restart it manually
          // because the $effect that watches currentTrack might not trigger on same ID
          if (String($currentTrack?.id) === String(nextTrack.id) && platform.player.ready()) {
              platform.player.seek(0);
              platform.player.play().catch(() => {});
          }
          currentTrack.set(nextTrack);
      }
      if ($syncMode !== 'off') {
        pushJamState();
      }
  }

  /**
   * Plays the previous track in the playlist.
   * Restarts the current track if it has played for more than 3 seconds.
   * Handles shuffle and repeat logic.
   */
  function playPrev() {
      // The service applies the same three-second rule itself (Media3's seekToPrevious).
      if ($playlist.length > 0 && sendTransportIntent('previous')) {
          logAction('player.previous', { trackId: $currentTrack?.id ?? null });
          return;
      }
      // If more than 3 seconds into the track, restart it
      if (platform.player.state().position > 3) {
          platform.player.seek(0);
          return;
      }

      const p = $playlist;
      if (p.length === 0) return;
      logAction('player.previous', { trackId: $currentTrack?.id ?? null });
      const currentTrackId = $currentTrack ? String($currentTrack.id) : null;
      const currentIndex = p.findIndex(t => String(t.id) === currentTrackId);

      let prevIndex;
      // Same guard as `playNext`: the service's shuffle order is not this component's to walk.
      if ($playerState.shuffle && !nativePlayback) {
          const stepped = stepBack(trailFor(p, currentTrackId));
          shuffleTrail = stepped.trail;
          prevIndex = p.findIndex(t => String(t.id) === stepped.id);
          if (prevIndex < 0) return;
      } else {
          prevIndex = currentIndex - 1;
          if (prevIndex < 0) {
              if ($playerState.repeat === 'all') {
                  prevIndex = p.length - 1;
              } else {
                  prevIndex = 0;
              }
          }
      }

      const prevTrack = p[prevIndex];
      if (prevTrack) {
          if ($syncMode === 'follower-jam') {
              // Remote control: send intent to play previous track
              pushJamState(true, prevTrack.id);
              return;
          }

          if (String($currentTrack?.id) === String(prevTrack.id) && platform.player.ready()) {
              platform.player.seek(0);
              platform.player.play().catch(() => {});
          }
          currentTrack.set(prevTrack);
      }
      if ($syncMode !== 'off') {
        pushJamState();
      }
  }

  /**
   * Handles the 'ended' event of the audio element.
   * Triggers scrobbling and plays the next track or repeats.
   */
  function handleEnded() {
      // A bulletin that runs out is the cue to resume, not to skip a track.
      // Browser only: on native the service restores the interrupted queue (and
      // re-tunes radio) itself and reports the result as an ordinary state
      // change, which `reconcileNativeRadioNews` and the native `command`
      // handling below already follow -- calling `stopNews()` here as well
      // would ask the service for a resume it already performed.
      if (newsSnapshot && !nativePlayback) {
          stopNews();
          return;
      }
      // Sent even when the halfway submission already fired: it carries the same timestamp, so it
      // corrects that listen's playing time to the whole track rather than adding a second listen.
      // A long set otherwise reports only the four minutes at which the first submission fired.
      scrobble(true);
      hasScrobbledFinished = true;
      // The service already moved on to the next item in its own queue and will
      // report it as a `command` event. Advancing here as well would ask it for
      // a second move -- two tracks skipped for one that ended.
      if (nativePlayback) return;
      if ($playerState.repeat === 'one') {
          platform.player.seek(0);
          platform.player.play();
      } else {
          playNext();
      }
  }

  /**
   * Follows a transport move the platform service already performed.
   *
   * Sent for a press on the notification, a head unit, a headset button and for
   * the end of a track. The queue is the service's, so there is nothing to
   * decide here: the UI is pointed at whatever the service says it is playing.
   * It must not call playNext/playPrev -- that would be the UI asking for a
   * move that already happened.
   *
   * Both halves of what the service said are read, with the newer winning: the
   * snapshot that travelled with the command, and anything it has sent since.
   * The plugin notifies the new state and then the move, as two bridge
   * messages, so a `next` read off the carried half alone can still be looking
   * at the track the service has already left. `trackAfterCommand` is what
   * closes that gap.
   *
   * @param {{name: string, seconds: number|null, state: object}} command
   */
  function handleNativeCommand(command) {
      const engine = { ...(command.state ?? {}), ...platform.player.state() };
      playerState.update(s => ({
          ...s,
          playing: engine.status === 'playing',
          progress: engine.position,
      }));

      // A report from before the newest queue position this side asked for (bug 095).
      if (nativeQueue?.isStale(engine.trackId)) return;
      const moved = trackAfterCommand($playlist, $currentTrack?.id ?? null, {
          name: engine.trackId != null ? "" : command.name,
          trackId: engine.trackId,
          queueLength: engine.queueLength,
      });
      if (!moved) return;
      followNativeTrack(moved);
  }

  /**
   * Points the UI at a track the service reported playing, without that turning into a request.
   *
   * The write to `currentTrack` re-runs the queue-sync effect; `follow` marks that one sync as a
   * mirror so it can never be sent back as "play this", however late the chain reaches it.
   *
   * @param {object} moved - The queue entry the service is on.
   */
  function followNativeTrack(moved) {
      hasScrobbledStarted = false;
      hasScrobbledFinished = false;
      nativeQueue?.follow(moved.id);
      currentTrack.set(moved);
  }

  /**
   * Toggles the mute state and manages volume transitions.
   */
  function toggleMute() {
    muted = !muted;
    if (muted) {
      lastVolume = $playerState.volume;
      platform.player.setVolume(0);
    } else {
      platform.player.setVolume(lastVolume / 100);
    }
  }

  /**
   * Handles time updates from the audio element.
   * Updates global player state, saves progress periodically, and handles mid-track scrobbling.
   */
  function handleTimeUpdate(state = platform.player.state()) {
    playerState.update(s => ({ ...s, progress: state.position }));
    reconcileNativeRadioNews(state);
    persistCurrentResumePosition();

    const length = currentLength(state);
    if (!hasScrobbledFinished && track && length > 0) {
        const threshold = Math.min(240, length / 2);
        if (state.position > threshold) {
            scrobble(true);
            hasScrobbledFinished = true;
        }
    }
  }

  /**
   * The length of whatever the element is playing, in seconds.
   *
   * Falling back to the track metadata is only right while the element plays
   * our own track: radio and a news bulletin put something else on it entirely,
   * and their length has nothing to do with the track that stays selected
   * underneath them.
   *
   * @param {object} [state] - The engine snapshot to read the length from.
   * @returns {number} A usable length, or 0 when nothing knows one.
   */
  function currentLength(state = platform.player.state()) {
    const own = !newsSnapshot && !$radioChannel;
    return resolveDuration(state.duration, own ? track?.duration : 0);
  }

  /**
   * Handles the engine's 'durationchange' event.
   * Sets track duration and restores saved progress if available.
   */
  function handleDurationChange(state = platform.player.state()) {
    // A settled native snapshot can change track without a directional command (shuffle,
    // recovery, or an index that never matched). Identity is authoritative here.
    if (nativePlayback && !nativeQueue?.isStale(state.trackId)) {
      const moved = trackAfterCommand($playlist, $currentTrack?.id, { trackId: state.trackId });
      if (moved) followNativeTrack(moved);
    }
    playerState.update(s => ({ ...s, duration: currentLength(state) }));
    // Restoring the last position is a browser-only move: there the element is
    // fresh and knows nothing. The platform service kept playing while this
    // WebView was gone, so seeking it to a position the UI remembers would
    // throw away the one it actually has -- the exact failure phase 1 exists to
    // prove does not happen.
    if (!initialized && track && !nativePlayback) {
        platform.player.seek($playerState.progress || 0);
        initialized = true;
    }
  }

  /**
   * Handles the 'play' event.
   * Updates playing state and triggers initial scrobble.
   */
  function handlePlay() {
    playerState.update(s => ({ ...s, playing: true }));
    if (!hasScrobbledStarted) {
        listenStartedAtMs = Date.now();
        scrobble(false);
        hasScrobbledStarted = true;
    }
    maybeOfferResume(track);
  }

  /**
   * The stream itself failed -- a missing file, a transcode that died, an
   * expired session. The audio element reports this on its own, without any
   * of the fetch calls in this component failing.
   */
  function handleAudioError() {
    if (!track) return;
    notify.error($t('notify.streamFailed', { title: track.title }));
  }

  /**
   * Handles the 'pause' event.
   * Updates playing state.
   */
  function handlePause() {
    playerState.update(s => ({ ...s, playing: false }));
    // `playerState` reaches localStorage at most every few seconds while playing; a pause is
    // where the position stops moving, so write it now rather than up to one interval later.
    flushPersistedStores();
    persistCurrentResumePosition(true);
  }

  /**
   * Writes one set's position into the account, if it is a set and the
   * position is worth keeping. Shared by every write site below rather than
   * each computing its own guard.
   *
   * @param {Object|null} targetTrack
   * @param {number} position - Seconds into `targetTrack`.
   */
  function persistResumePositionFor(targetTrack, position) {
    if (!targetTrack || !isSet(targetTrack)) return;
    saveSetResumePosition(resumeKeyFor(targetTrack), position).catch((e) =>
      console.warn('Could not save the resume position', e));
  }

  /**
   * Writes the current set's position, throttled to once every
   * `RESUME_WRITE_INTERVAL_MS` unless `force` -- pause, a track change and
   * `beforeunload` all want the write to happen right away, the periodic
   * `timeupdate` tick does not.
   *
   * Radio and a bulletin are excluded through `isSetMode`, which already
   * carries the same `own` gate `currentLength()` uses -- neither is really
   * "the selected track", and writing under its key would corrupt whatever
   * set that key actually belongs to.
   *
   * @param {boolean} [force=false]
   */
  function persistCurrentResumePosition(force = false) {
    if (!isSetMode) return;
    const now = Date.now();
    if (!force && now - lastResumeWriteAt < RESUME_WRITE_INTERVAL_MS) return;
    lastResumeWriteAt = now;
    persistResumePositionFor(track, platform.player.state().position);
  }

  /**
   * Offers to resume a set, once per track: seeks straight to the stored
   * position (rather than waiting for a tap) and raises a dismissable toast
   * with an "opnieuw" action, so starting over is one tap rather than a
   * fight with the scrub bar. Guarded by `resumeOfferedTrackId` so pausing
   * and pressing play again on the same set does not ask a second time.
   *
   * @param {Object|null} currentTrackRef
   */
  async function maybeOfferResume(currentTrackRef) {
    if (!currentTrackRef || !isSet(currentTrackRef)) return;
    if (resumeOfferedTrackId === currentTrackRef.id) return;
    resumeOfferedTrackId = currentTrackRef.id;
    try {
      const all = await loadSetResumePositions();
      const entry = all[resumeKeyFor(currentTrackRef)];
      if (!shouldResume(entry, currentTrackRef.duration)) return;
      // The current track may have moved on while this was in flight.
      if ($currentTrack?.id !== currentTrackRef.id) return;
      const target = entry.position;
      logAction('player.resumeOffered', { trackId: currentTrackRef.id, seconds: target });
      platform.player.seek(target);
      playerState.update((s) => ({ ...s, progress: target }));
      notify.info($t('notify.resumeAt', { time: formatClock(target) }), {
        action: {
          label: $t('notify.resumeRestart'),
          onClick: () => {
            platform.player.seek(0);
            playerState.update((s) => ({ ...s, progress: 0 }));
          },
        },
      });
    } catch (e) {
      console.warn('Could not read the resume position', e);
    }
  }

  /**
   * Handles the 'volumechange' event.
   * Updates global player volume state.
   */
  function handleVolumeChange(state = platform.player.state()) {
    playerState.update(s => ({ ...s, volume: state.volume * 100 }));
  }

  /**
   * Seeks to an absolute position, in seconds, clamped to the track's length.
   *
   * The one path every other seek goes through: a click on the songs-mode
   * bar, a drag on the sets-mode range input, and the ±30 s buttons. Kept
   * separate from `seek(e)` below because the range input and the skip
   * buttons already have seconds, not a mouse event to compute them from.
   *
   * @param {number} seconds
   */
  function seekTo(seconds) {
    if (duration <= 0 || !Number.isFinite(seconds)) return;
    const clamped = Math.max(0, Math.min(duration, seconds));
    logAction('player.seek', { trackId: track?.id ?? null, seconds: Math.round(clamped) });
    platform.player.seek(clamped);
    if ($syncMode !== 'off') {
      pushJamState();
    }
  }

  /**
   * Seeks to a specific position in the track based on a click event on the progress bar.
   *
   * @param {MouseEvent} e - The click event.
   */
  function seek(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = x / rect.width;
    // Not the engine's own length: a chunked stream leaves that at 0, and the
    // bar is drawn from the track's length instead -- seek to the same one.
    if (duration <= 0) return;
    seekTo(percentage * duration);
  }

  /**
   * Jumps the current position by a number of seconds, forward or back. Sets
   * mode's ±30 s buttons and the sets-mode scrub bar's arrow keys, on both the
   * desktop bar and Now Playing.
   *
   * @param {number} deltaSeconds
   */
  function skip(deltaSeconds) {
    if (!platform.player.ready()) return;
    seekTo(platform.player.state().position + deltaSeconds);
  }

  /**
   * Changes the volume based on a click event on the volume bar.
   *
   * @param {MouseEvent} e - The click event.
   */
  function changeVolume(e) {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const vol = Math.max(0, Math.min(1, x / rect.width));
      platform.player.setVolume(vol);
      muted = (vol === 0);
  }


  /**
   * Cycles through repeat modes: none -> all -> one -> none.
   *
   * Native only: pushed to the platform service instead of only the local store. The service
   * decides repeat for itself there -- see `nativePlayback` -- so the cycle is not assumed to have
   * landed; the store mirrors back whatever `setMode` says was actually applied.
   */
  function toggleRepeat() {
      const next = $playerState.repeat === 'none' ? 'all' : $playerState.repeat === 'all' ? 'one' : 'none';
      if (nativePlayback) {
          platform.player.setMode({ shuffle: $playerState.shuffle, repeat: next })
              .then(mode => playerState.update(s => ({ ...s, shuffle: mode.shuffle, repeat: mode.repeat })))
              .catch(e => console.error('Could not set the native repeat mode', e));
          return;
      }
      playerState.update(s => ({ ...s, repeat: next }));
  }

  /**
   * Toggles the shuffle mode.
   *
   * Native only: same hand-off as `toggleRepeat`, and `shuffleTrail` is left untouched -- it is
   * `playNext`/`playPrev`'s own bookkeeping for walking a JS-decided shuffle order, and on a
   * native shell the service has a shuffle order of its own that this component never sees.
   */
  function toggleShuffleMode() {
      const next = !$playerState.shuffle;
      if (nativePlayback) {
          platform.player.setMode({ shuffle: next, repeat: $playerState.repeat })
              .then(mode => playerState.update(s => ({ ...s, shuffle: mode.shuffle, repeat: mode.repeat })))
              .catch(e => console.error('Could not set the native shuffle mode', e));
          return;
      }
      playerState.update(s => ({ ...s, shuffle: next }));
      // A fresh run of shuffle starts its trail here, so the first "previous"
      // after switching it on goes back to the track that was playing.
      shuffleTrail = startTrail($currentTrack?.id);
  }

  /**
   * Toggles the sync mode: off -> host -> follower-jam -> follower-radio -> off.
   */
  function toggleJamMode() {
      syncMode.update(m => {
          if (m === 'off') return 'host';
          if (m === 'host') return 'follower-jam';
          if (m === 'follower-jam') return 'follower-radio';
          return 'off';
      });
  }

  /**
   * Increases the volume by 5%.
   */
  function volumeUp() {
    if (!platform.player.ready()) return;
    platform.player.setVolume(platform.player.state().volume + 0.05);
    muted = false;
  }

  /**
   * Decreases the volume by 5%.
   */
  function volumeDown() {
    if (!platform.player.ready()) return;
    platform.player.setVolume(platform.player.state().volume - 0.05);
    if (platform.player.state().volume === 0) muted = true;
  }

  /**
   * Toggles full-screen mode for the application.
   */
  function toggleFullScreen() {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(e => console.error("Fullscreen failed", e));
    } else if (document.exitFullscreen) {
      document.exitFullscreen();
    }
  }

  /**
   * Navigates to the album of the current track and highlights it.
   */
  function goToAlbum() {
    if (track && track.albumId) {
      highlightedTrackId.set(track.id);
      onnavigate(`album:${track.albumId}`);
    }
  }

  /**
   * Opens the full-screen Now Playing view for a tap on the mobile mini
   * player -- everywhere on it except the play/pause and next buttons, which
   * are real `<button>`s nested inside the same tappable row and keep their
   * own action instead.
   *
   * @param {MouseEvent} e
   */
  function handleMiniPlayerTap(e) {
    if (e.target.closest('button')) return;
    if (!track) return;
    openNowPlaying();
  }

  const track = $derived($radioChannel && $radioNowPlaying
    ? {
        id: $radioNowPlaying.track_id,
        title: $radioNowPlaying.title,
        artist: $radioNowPlaying.artist,
        album: $radioNowPlaying.album,
        coverArt: $radioNowPlaying.cover_art,
      }
    : $currentTrack);
  // Read from the shared rating store (`ratings.js`), so a rating set in the track list, car mode
  // or the details sheet repaints the player too. `track` on radio is built fresh from the
  // timeline entry, which is why this cannot live on `track.userRating` alone.
  const currentRating = $derived(ratingFor($ratings, track));

  const primaryArtist = $derived(primaryArtistOf(track));
  const playing = $derived($playerState.playing);
  const progress = $derived(track ? $playerState.progress : 0);
  // Radio and a news bulletin are not the selected track, so they get no
  // fallback length; see currentLength().
  const fallbackLength = $derived((newsSnapshot || $radioChannel) ? 0 : (track?.duration ?? 0));
  const duration = $derived(track ? resolveDuration($playerState.duration, fallbackLength) : 0);
  // Whether the sets-mode player chrome applies: ±30 s buttons, h:mm:ss time
  // labels, the fine-grained scrub bar. Radio and a bulletin are never a set
  // regardless of their nominal track's duration -- the same gate
  // `currentLength()` uses, because neither is really "the selected track".
  const isSetMode = $derived(!newsSnapshot && !$radioChannel && isSet(track));
  const volume = $derived($playerState.volume);
  const repeatMode = $derived($playerState.repeat);
  const shuffleMode = $derived($playerState.shuffle);

  /**
   * Where `track` sits in the queue, for `NowPlaying.svelte`'s continuation sections (increment
   * F, "next up" and `addAfterCurrent`) -- -1 when there is nothing to point at.
   *
   * Native: the position `nativeQueue` last pushed or adopted, since the service is the one
   * actually walking the queue and this component only mirrors it (see `nativeQueue.js`'s
   * `currentIndex`). `nativeQueuePositionTick` is read only to give this a reason to
   * recompute after that position changes -- `nativeQueue` itself is a plain variable, not a
   * store, so Svelte would otherwise never know to look again.
   * Browser: a lookup by id, the same thing `playNext`/`playPrev` already do to find where they
   * are -- there is no second, independent position to mirror.
   */
  const queueIndex = $derived.by(() => {
    if (nativePlayback) {
      void nativeQueuePositionTick;
      return nativeQueue?.currentIndex() ?? -1;
    }
    return $playlist.findIndex((t) => String(t.id) === String($currentTrack?.id));
  });
  const syncColor = $derived(
    $syncMode === 'host' ? '#1db954' : 
    ($syncMode === 'follower-jam' ? '#3d91ff' : 
    ($syncMode === 'follower-radio' ? '#b266ff' : '#b3b3b3'))
  );
  const syncTitle = $derived(
    $syncMode === 'host' ? $t('player.syncHost') :
    ($syncMode === 'follower-jam' ? $t('player.syncRemote') :
    ($syncMode === 'follower-radio' ? $t('player.syncListener') : $t('player.syncOff')))
  );
  const isRadioActive = $derived($radioChannel !== null);
  const radioColor = $derived($radioChannel ? '#b266ff' : '#b3b3b3');
  const newsColor = $derived(newsSnapshot ? '#b266ff' : '#b3b3b3');
  // Radio listeners cannot steer the stream, exactly like a follower-radio client.
  const transportLocked = $derived($syncMode === 'follower-radio' || isRadioActive);
  const releaseDate = $derived(track ? releaseDateLabel(track) : '');
  // `coverArtSrc` is the one place that knows whether this device has a local,
  // offline copy of the art; going through it here means the mini player and
  // the full-screen one no longer build `/rest/getCoverArt` URLs by hand and
  // agree with every other list in the app about what "offline" shows.
  // `coverArtSrc` answers a missing id with `FALLBACK` (the MuMa mark svg),
  // but `Artwork` needs `null` for "no cover" so it can fall through to the
  // artist image instead of rendering that mark as if it were the cover.
  const coverUrl = $derived.by(() => {
    const src = coverArtSrc(track?.coverArt, 100, $authParams, $localCoverArt, $offline);
    return src === FALLBACK ? null : src;
  });
  const fullCoverUrl = $derived.by(() => {
    const src = coverArtSrc(track?.coverArt, 512, $authParams, $localCoverArt, $offline);
    return src === FALLBACK ? null : src;
  });
  // The same cover -> portrait -> panel chain every track row uses, including its memory of
  // portraits MuMa has already said it does not have.
  const artistUrl = $derived(artistImageFallback(track, $authParams));
  const tint = $derived(trackTint(track, genreTints));
  // Offline, the art lives on disk and `coverArtSrc` only knows that once the
  // shell has been asked; a no-op online, so the player pays nothing there.
  $effect(() => {
    if (track?.coverArt) resolveCoverArt([track.coverArt]);
  });
  const streamUrl = $derived(track?.id ? restUrl(`/rest/stream?id=${track.id}&${$authParams}`) : '');

  // What the notification, the lock screen and a car head unit show. The engine
  // owns the OS integration; this is the only thing it cannot work out for
  // itself, because the artwork URL carries our credentials and the fallback
  // length comes from the library rather than the stream.
  $effect(() => {
    if (!track) return;
    platform.player.setNowPlaying({
      title: track.title || $t('player.unknownTrack'),
      artist: track.artist || $t('player.unknownArtist'),
      album: track.album || $t('player.unknownAlbum'),
      artworkUrl: track.coverArt
        ? restUrl(`/rest/getCoverArt?id=${track.coverArt}&size=512&${$authParams}`)
        : window.location.origin + '/images/spotify-fallback.svg',
      duration: fallbackLength,
    });
  });

  $effect(() => {
    let interval;
    if ($syncMode !== 'off') {
        interval = setInterval(syncJam, 4000);
        syncJam();
    }
    return () => {
        if (interval) clearInterval(interval);
    };
  });

  $effect(() => {
    // Explicitly depend on state that should trigger a sync
    const _p = $playlist;
    const _t = track;
    const _pl = playing;

    if (shouldPushJamState($syncMode, isSyncing, $credentials.username)) {
        pushJamState();
    }
  });

  let lastTrackId = null;
  let hasScrobbledStarted = false;
  let hasScrobbledFinished = false;
  let initialized = false;
  /** Whether the platform queue has been synced at least once this session. */
  let nativeQueueSynced = false;

  /** How often a playing set's position is written to the account, in ms. */
  const RESUME_WRITE_INTERVAL_MS = 15000;
  /** `Date.now()` of the last resume write, so `persistCurrentResumePosition` can throttle. */
  let lastResumeWriteAt = 0;
  /** The track `maybeOfferResume` last decided about, so pausing and pressing play again does not ask twice. */
  let resumeOfferedTrackId = null;
  /** The track this component is tracking a resume position for -- the previous value of `track`, kept for the write on the way out when it changes. */
  let previousTrackForResume = null;

  /**
   * When this play of the current track began, in milliseconds.
   *
   * Sent with every submission for the track, so the server keys them all to the same listen. The
   * first submission fires halfway through and reports the seconds played so far; a later one --
   * when the track ends -- reports the real total and updates that same listen rather than adding a
   * second one. Without a client-set timestamp the server would stamp each submission with its own
   * clock and record two listens.
   */
  let listenStartedAtMs = null;

  /**
   * Sends a scrobble request to the server.
   *
   * @param {boolean} [submission=true] - Whether this is a final submission or just a "now playing" notification.
   */
  async function scrobble(submission = true) {
    // On the native shell the platform service scrobbles every track itself (source `mobile` or
    // `auto`), and keeps doing so while this WebView sleeps. Scrobbling here as well recorded each
    // listen twice under two timestamps the server cannot pair up, and the copies sent from a
    // backgrounded WebView failed or arrived late with a stale start time.
    if (nativePlayback) return;
    if (!track || !$credentials.username) return;
    const params = $authParams;
    // How long this track actually played, and where. Both are MuMa's own parameters rather than
    // Subsonic ones; a listen without them records only that something was played, which cannot be
    // turned into listening time for a collection whose average track is a quarter of an hour.
    // Only a submission has a playing time to report -- a "now playing" ping fires at the start.
    const playedSeconds = submission ? Math.floor(platform.player.state().position) : null;
    let extra = playedSeconds ? `&playedSeconds=${playedSeconds}` : '';
    if (submission && listenStartedAtMs) extra += `&time=${listenStartedAtMs}`;
    const url = restUrl(`/rest/scrobble?id=${track.id}&submission=${submission}&source=frontend${extra}&${params}`);
    try {
      const failure = await subsonicError(await fetch(url));
      if (failure) {
        // A lost scrobble does not interrupt playback, so it is a warning
        // rather than an error -- but it is silent otherwise, and a listening
        // history with holes in it is what people notice weeks later.
        notify.warning($t('notify.scrobbleFailed'), { detail: failure.message });
      }
    } catch (e) {
      console.error("Scrobble failed", e);
      notify.warning($t('notify.scrobbleFailed'), { detail: e.message });
    }
  }

  /**
   * A tap on star `rating` for the current track: sets it, or clears it when it is already that
   * many stars. The write, the optimistic update and the rollback live in `ratings.js`.
   *
   * @param {number} rating - The star tapped (1-5).
   */
  function updateRating(rating) {
    if (!track) return;
    tapStar(track, rating);
  }

  /** Whether the last run of the queue-sync effect below found radio or a bulletin on. */
  let wasRadioOrNews = false;

  // The queue as the platform service should hold it. Native only: in a browser
  // `sync` is never called and the queue stays exactly where it always was, in
  // the `playlist` store. Reads both stores before the readiness check so the
  // effect re-runs once the engine is up.
  $effect(() => {
    const queue = $playlist;
    // The whole track, not its id: it is not always in the queue -- a card on
    // the home screen sets the current track and nothing else -- and the
    // service needs a title and an artist to put in the notification.
    const wanted = $currentTrack ?? null;
    // Radio and a bulletin own the service's single-item queue while either is
    // on; pushing the ordinary one over it would replace whatever is actually
    // playing. `toggleRadio`/`toggleNews`'s own service calls handle turning
    // either off -- this effect only has to stay out of the way while they are
    // running and resync once they are not.
    const radioOrNewsActive = Boolean($radioChannel) || Boolean(newsSnapshot);
    if (!nativePlayback || !engineReady || !nativeQueue) {
      wasRadioOrNews = radioOrNewsActive;
      return;
    }
    if (radioOrNewsActive) {
      wasRadioOrNews = true;
      return;
    }
    // Coming back from radio or a bulletin must not resume playback on its
    // own: turning radio off already leaves the service silent
    // (`toggleRadio`'s `pause()`), and a bulletin already resumed itself, on
    // the far side, at the position it interrupted
    // (`NewsPlaybackController.stopAndRestore`). Pushing the queue again here
    // with `autoplay: true` would fight either.
    const justLeftRadioOrNews = wasRadioOrNews;
    wasRadioOrNews = false;
    // The first sync after a boot must not start the music: what is in the
    // stores then is either what the service was already playing (in which case
    // nothing is sent at all) or a queue restored from localStorage, and an app
    // that starts playing the moment it is opened is a bug people notice at
    // night.
    const autoplay = justLeftRadioOrNews ? false : nativeQueueSynced;
    nativeQueueSynced = true;
    // An empty queue at boot is not an instruction to clear the service's: it
    // means the rehydrate found nothing to restore, which is no reason to stop
    // music that is playing.
    if (!autoplay && queue.length === 0) return;
    // See `queueIndex`: this is the only thing that gives it a reason to look at
    // `nativeQueue.currentIndex()` again once this settles.
    nativeQueue.sync(queue, wanted, { autoplay }).then(() => nativeQueuePositionTick++);
  });

  $effect(() => {
    if (track && track.id !== lastTrackId) {
        const isInitialLoad = !lastTrackId && !initialized;
        // Writes wherever the outgoing track (not the one about to play) was
        // left, before the engine's position means something else. Reads
        // `platform.player.state()` rather than `progress`: the engine has not
        // been told to load the new track yet at this point in the effect, so
        // its position is still the outgoing track's.
        if (!isInitialLoad) {
          persistResumePositionFor(previousTrackForResume, platform.player.state().position);
        }
        previousTrackForResume = track;
        lastTrackId = track.id;
        hasScrobbledStarted = false;
        hasScrobbledFinished = false;

        // The service owns what plays; the queue effect above is what tells it.
        // Loading a stream URL here as well would be the second engine.
        if (nativePlayback) return;

        // Don't load audio in remote-only jam mode
        if ($syncMode === 'follower-jam') return;
        // Radio owns the audio element while it is on; the controller decides
        // what to load and at which offset.
        if ($radioChannel) return;
        // A bulletin owns it too, and hands it back itself when it ends.
        if (newsSnapshot) return;

        if (platform.player.ready()) {
            platform.player
              .load({ url: streamUrl, trackId: track.id, autoplay: !isInitialLoad })
              .catch(e => {
                  // An AbortError is the previous track's play() being
                  // cancelled by this one, which is what skipping does --
                  // not something to report.
                  if (e.name !== 'AbortError') {
                      console.error("Auto-play failed", e);
                      notify.error($t('notify.playbackFailed'), { detail: e.message });
                  }
              });
        }
    }
  });

  onMount(() => {
    // The element is rendered here and driven by the engine from now on. On a
    // native shell nothing is handed over and the platform service plays
    // instead; that is the whole point of the hand-off.
    platform.player.attach(audioElement ?? null);
    if (nativePlayback) {
      // The service has a volume of its own and it outlived this WebView, so
      // the UI follows it rather than pushing a remembered number at it. Shuffle
      // and repeat are the same story: a restored session may already have
      // either set, and the store should show what the service is actually
      // doing rather than the defaults this component starts with.
      const native = platform.player.state();
      playerState.update(s => ({
        ...s,
        volume: native.volume * 100,
        shuffle: native.shuffle,
        repeat: native.repeat,
      }));
      // Radio or a bulletin may already be running -- started before this
      // WebView existed, or surviving its recreation. Recognising it here,
      // before `engineReady` flips true below, is what keeps the queue-sync
      // effect from immediately pushing a stale queue over it.
      reconcileNativeRadioNews(native);
      // Take over the queue that is already there before any effect pushes one.
      // Both go on the same chain, so the adopt always wins the race.
      nativeQueue = createNativeQueue(platform.player, {
        artworkUrlFor: (entry) => (entry.coverArt
          ? restUrl(`/rest/getCoverArt?id=${entry.coverArt}&size=512&${$authParams}`)
          : ''),
        onError: (e) => console.error('Could not hand the queue to the player service', e),
      });
      // See `queueIndex`: the adopted position is otherwise invisible to it until something
      // else happens to touch `nativeQueuePositionTick`.
      nativeQueue.adopt().then(() => nativeQueuePositionTick++);
    } else {
      platform.player.setVolume(volume / 100);
    }
    engineReady = true;

    // The queue lives in this component, so the transport controls outside the
    // app come back to it.
    platform.player.setCommandHandlers({
      play: togglePlay,
      pause: togglePlay,
      previous: playPrev,
      next: playNext,
      seekTo: (seconds) => platform.player.seek(seconds),
    });

    const unsubscribes = [
      platform.player.on('timeupdate', handleTimeUpdate),
      platform.player.on('durationchange', handleDurationChange),
      platform.player.on('play', handlePlay),
      platform.player.on('pause', handlePause),
      platform.player.on('volumechange', handleVolumeChange),
      platform.player.on('ended', handleEnded),
      platform.player.on('error', handleAudioError),
      // Never fires in a browser; on a native shell it is how a press on the
      // notification, a head unit or a headset reaches the UI.
      platform.player.on('command', handleNativeCommand),
    ];

    if (track && !initialized && !nativePlayback) {
        // The position is restored on 'durationchange'.
        platform.player.load({ url: streamUrl, trackId: track.id });
    }

    const handleGlobalKeyDown = (e) => {
      // Ignore if typing in an input field
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) {
        return;
      }

      switch (e.key) {
        case '5':
        case 'MediaPlayPause':
          togglePlay();
          break;
        case '4':
        case 'MediaTrackPrevious':
          playPrev();
          break;
        case '6':
        case 'MediaTrackNext':
          playNext();
          break;
        case '2':
        case 'VolumeUp':
          volumeUp();
          break;
        case '8':
        case 'VolumeDown':
          volumeDown();
          break;
        case '0':
        case 'VolumeMute':
          toggleMute();
          break;
        case ' ':
          e.preventDefault();
          togglePlay();
          break;
        case 'f':
        case 'F':
          toggleFullScreen();
          break;
        case 'Escape':
        case 'Backspace':
          if (window.history.length > 1) {
            window.history.back();
          }
          break;
        case 'Red':
        case 'ColorF0Red':
          activeView.set('home');
          break;
        case 'Green':
        case 'ColorF1Green':
          activeView.set('songs');
          break;
        case 'Yellow':
        case 'ColorF2Yellow':
          activeView.set('sets');
          break;
        case 'Blue':
        case 'ColorF3Blue':
          activeView.set('settings');
          break;
      }
    };

    const handleGlobalWheel = (e) => {
      // MX Master 3 thumb wheel sends deltaX. 
      // We use a threshold to avoid accidental triggers.
      if (Math.abs(e.deltaX) > 20) {
        if (e.deltaX > 0) volumeDown();
        else volumeUp();
      }
    };

    // The last chance to record a set's position: a reload or a closed tab
    // gives none of the periodic or track-change writes above a chance to
    // run first.
    const handleBeforeUnload = () => persistCurrentResumePosition(true);

    window.addEventListener('wheel', handleGlobalWheel, { passive: true });
    window.addEventListener('keydown', handleGlobalKeyDown);
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeyDown);
      window.removeEventListener('wheel', handleGlobalWheel);
      window.removeEventListener('beforeunload', handleBeforeUnload);
      if (radioTickInterval) clearInterval(radioTickInterval);
      if (radioRefreshInterval) clearInterval(radioRefreshInterval);
      if (radioClockInterval) clearInterval(radioClockInterval);
      for (const unsubscribe of unsubscribes) unsubscribe();
      platform.player.detach();
    };
  });
</script>

<!--
  The element the browser engine drives. `crossorigin` has to be on it from the
  first byte or the Web Audio equalizer may not read it. Everything else about
  it -- events, source, transport -- is `platform.player`'s.

  Absent inside the Android shell, and that is a rule rather than an
  optimisation: `document.querySelector('audio')` being null there is what makes
  "two engines can never play at once" checkable instead of merely intended.
-->
{#if !nativePlayback}
  <audio bind:this={audioElement} crossorigin="anonymous"></audio>
{/if}

<footer class="flex items-center h-full px-2 md:px-4 relative">
  {#if $isMobile}
    <!-- Mobile Mini Player. A tap anywhere on it opens Now Playing, except on the
         play/pause and next buttons -- those are real <button>s inside this same
         row and keep their own action; `handleMiniPlayerTap` is what tells the
         two apart. Album navigation (`goToAlbum`, still used by the desktop
         player below) moves to that full-screen view instead of firing here. -->
    <div
      class="flex flex-1 items-center gap-3 min-w-0 py-2 h-full {track ? 'cursor-pointer' : ''}"
      role="button"
      tabindex="0"
      onclick={handleMiniPlayerTap}
      onkeydown={(e) => e.key === 'Enter' && handleMiniPlayerTap(e)}
    >
      {#if track}
        <!-- One square slot, cover -> artist image -> tinted panel (`Artwork.svelte`); the
             separate round artist avatar that used to sit next to the artist name is gone,
             its job absorbed into this same fallback chain. `shrink-0` keeps it 44px
             regardless of how tight the row gets on a narrow phone. -->
        <Artwork
          class="w-11 h-11 shrink-0 shadow-lg"
          rounded="rounded"
          {coverUrl}
          {artistUrl}
          {tint}
          title={track.title}
          alt={track.title}
        />
        <div class="flex-1 min-w-0">
          <div class="text-[13px] font-bold text-white truncate">{track.title}</div>
          <div class="text-[11px] text-muma-spotify-text truncate">{track.artist}</div>
        </div>
        <div class="flex items-center gap-0.5 flex-shrink-0">
          {#each [1, 2, 3, 4, 5] as star (star)}
            <button
              aria-label="{star} sterren"
              class="bg-transparent border-none p-0 cursor-pointer transition-colors { currentRating >= star ? 'text-brand' : 'text-white/10' }"
              onclick={() => updateRating(star)}
            >
              <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
              </svg>
            </button>
          {/each}
        </div>
      {:else}
        <div class="flex-1 flex items-center gap-3 min-w-0">
          <div class="w-11 h-11 bg-white/5 rounded flex items-center justify-center">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="#535353">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 14.5c-2.49 0-4.5-2.01-4.5-4.5S9.51 7.5 12 7.5s4.5 2.01 4.5 4.5-2.01 4.5-4.5 4.5zm0-7c-1.38 0-2.5 1.12-2.5 2.5s1.12 2.5 2.5 2.5 2.5-1.12 2.5-2.5-1.12-2.5-2.5-2.5z"></path>
            </svg>
          </div>
          <div class="text-[13px] text-muma-spotify-text italic font-medium">{$t('player.nothingPlaying')}</div>
        </div>
      {/if}
      <div class="flex items-center gap-3 px-2">
        {#if equalizerSupported}
          <button
            data-eq-toggle
            class="bg-transparent border-none p-0 cursor-pointer transition-colors {$equalizerSettings.enabled ? 'text-brand' : 'text-muma-spotify-text'}"
            onclick={() => (showEqualizer = !showEqualizer)}
            aria-label={$t('equalizer.title')}
            aria-pressed={showEqualizer}
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M4 20V14M4 10V4M12 20V12M12 8V4M20 20V16M20 12V4M1 14h6M9 8h6M17 16h6"></path>
            </svg>
          </button>
        {/if}
        <button
          class="bg-transparent border-none p-0 text-white hover:scale-105 transition-transform {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={togglePlay} 
          disabled={transportLocked}
          aria-label={playing ? $t('player.pause') : $t('common.play')}
        >
          {#if playing}
            <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
              <path d="M5.7 3a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7H5.7zm10 0a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
              <path d="M7.05 3.606l13.49 7.788a.7.7 0 0 1 0 1.212L7.05 20.394A.7.7 0 0 1 6 19.788V4.212a.7.7 0 0 1 1.05-.606z"></path>
            </svg>
          {/if}
        </button>
        {#if track}
          <button 
            class="bg-transparent border-none p-0 text-muma-spotify-text hover:text-white transition-colors {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}" 
            onclick={playNext} 
            disabled={transportLocked}
            aria-label={$t('player.next')}
          >
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
              <path d="M16.7 3.3a.7.7 0 0 0-.7.7v6.85L6.05 4.806A.7.7 0 0 0 5 5.412v13.175a.7.7 0 0 0 1.05.607L16 13.15v6.85a.7.7 0 0 0 .7.7h1.6a.7.7 0 0 0 .7-.7V4a.7.7 0 0 0-.7-.7h-1.6z"></path>
            </svg>
          </button>
        {/if}
      </div>
    </div>
    <!-- Progress bar for mobile -->
    {#if track}
      <div class="absolute top-0 left-0 w-full h-[2px] bg-white/10">
        <div class="h-full bg-white transition-[width] duration-100" style="width: {progressPercent(progress, duration)}%"></div>
      </div>
    {/if}
    {#if showEqualizer}
      <div bind:this={equalizerPanelEl} class="fixed inset-x-0 bottom-0 z-50 flex justify-center p-3 pb-24">
        <Equalizer onclose={() => (showEqualizer = false)} />
      </div>
    {/if}
    <!-- Reuses everything this component already computed for the mini player --
         rating, transport, shuffle/repeat -- rather than a second copy of that
         state. Its own queue button goes through the same `ontoggleQueue` the
         mini player never exposed a button for, so it opens the one queue view
         App.svelte already renders (a bottom sheet on the phone). -->
    <NowPlaying
      open={$nowPlayingOpen}
      {track}
      {playing}
      {progress}
      {duration}
      rating={currentRating}
      {shuffleMode}
      {repeatMode}
      {queueIndex}
      {transportLocked}
      coverUrl={fullCoverUrl}
      {artistUrl}
      {tint}
      {equalizerSupported}
      {outputRoute}
      {isSetMode}
      {lyricsLines}
      onclose={closeNowPlaying}
      ontogglePlay={togglePlay}
      onnext={playNext}
      onprev={playPrev}
      onrate={updateRating}
      ontoggleShuffle={toggleShuffleMode}
      ontoggleRepeat={toggleRepeat}
      onseek={seek}
      onseekTo={seekTo}
      onskip={skip}
      ontoggleEqualizer={() => (showEqualizer = !showEqualizer)}
      {ontoggleQueue}
      onopenOutputPicker={openOutputPicker}
      radioActive={isRadioActive}
      {radioChannels}
      {showRadioPicker}
      ontoggleRadio={toggleRadio}
      onstartRadio={startRadio}
      oncloseRadioPicker={() => (showRadioPicker = false)}
      newsActive={newsSnapshot !== null}
      ontoggleNews={toggleNews}
      {onnavigate}
    />
  {:else}
    <!-- Desktop Player -->
    <div class="w-[30%] hidden md:flex items-center gap-3">
      {#if track}
        <!-- Desktop keeps its own plain `<img>`: `coverUrl` is `null` for "no cover" now that
             `Artwork.svelte` (the mobile mini player and the full-screen view) owns the
             cover -> artist -> panel fallback, so this one substitutes the MuMa mark itself
             rather than rendering a broken image. -->
        <img src={coverUrl ?? FALLBACK} alt={track.title} class="w-14 h-14 rounded" onerror={(e) => e.target.src = FALLBACK} />
        <div class="track-info min-w-0">
          <div
            role="button"
            tabindex="0"
            class="text-sm font-medium truncate hover:underline cursor-pointer"
            onclick={goToAlbum}
            onkeydown={(e) => e.key === 'Enter' && goToAlbum()}
          >{track.title}</div>
          <div class="flex items-center gap-1.5 min-w-0">
            {#if primaryArtist}
              <img
                src={getArtistImageUrl(primaryArtist, $authParams)}
                alt={primaryArtist.name}
                class="w-5 h-5 rounded-full object-cover flex-shrink-0"
                onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
              />
            {/if}
            <ArtistList
              artist={track.artist}
              artistId={track.artistId}
              artists={track.artists}
              onnavigate={onnavigate}
            />
          </div>
        </div>
      {/if}
    </div>

    <div class="flex-1 md:w-[40%] max-w-[600px] flex flex-col items-center gap-2">
      <div class="flex items-center gap-4 md:gap-6">
        <button class="hidden md:flex flex-col items-center bg-transparent border-none p-0 cursor-pointer transition-colors hover:text-white {shuffleMode ? 'text-brand' : 'text-muma-spotify-text'}" onclick={toggleShuffleMode} aria-label={$t('queue.shuffle')}>
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M13.151.922a.75.75 0 1 0-1.06 1.06L13.109 3H10.3a5 5 0 0 0-4.054 2.115L2.615 10H1.25a.75.75 0 0 0 0 1.5h2.185a5 5 0 0 0 4.054-2.115L11.121 5H13.11l-1.019 1.017a.75.75 0 1 0 1.06 1.06L15.424 4.8a.75.75 0 0 0 0-1.06L13.15 1.472a.75.75 0 0 0-.001-.55zM13.151 9.922a.75.75 0 1 0-1.06 1.06L13.109 12H11.12l-1.144-1.636a.75.75 0 1 0-1.232.862l1.378 1.968A5 5 0 0 0 14.176 13.5h.194l-1.269 1.271a.75.75 0 1 0 1.06 1.06L16.43 13.56a.75.75 0 0 0 0-1.06l-2.274-2.273a.75.75 0 0 0-1.005-.305zM5.185 3.5h1.077L7.406 5.137a.75.75 0 0 0 1.232-.863l-1.378-1.967A5 5 0 0 0 3.235 1.5H1.25a.75.75 0 0 0 0 1.5h2.185a3.5 3.5 0 0 1 2.838 1.48L5.185 3.5z"></path>
          </svg>
          {#if shuffleMode}
            <div class="w-1 h-1 bg-brand rounded-full mt-0.5"></div>
          {/if}
        </button>
        <button
          class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-muma-spotify-text {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={playPrev}
          disabled={transportLocked}
          aria-label={$t('player.previous')}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M3.3 1a.7.7 0 0 1 .7.7v5.15l9.95-5.744a.7.7 0 0 1 1.05.606v12.575a.7.7 0 0 1-1.05.607L4 9.15v5.15a.7.7 0 0 1-.7.7H1.7a.7.7 0 0 1-.7-.7V1.7a.7.7 0 0 1 .7-.7h1.6z"></path>
          </svg>
        </button>
        {#if isSetMode}
          <button
            class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-muma-spotify-text {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
            onclick={() => skip(-30)}
            disabled={transportLocked}
            aria-label={$t('player.skipBack')}
            title={$t('player.skipBack')}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <path d="M12 5V1L7 6l5 5V7a6 6 0 1 1-6 6H5a7 7 0 1 0 7-7z"></path>
            </svg>
            <span class="text-[8px] font-bold -ml-1">30</span>
          </button>
        {/if}
        <button
          class="w-9 h-9 bg-white rounded-full text-black flex items-center justify-center cursor-pointer transition-transform hover:scale-105 {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={togglePlay}
          disabled={transportLocked}
        >
          {#if playing}
            <svg viewBox="0 0 16 16" width="16" height="16" fill="black">
              <path d="M2.7 1a.7.7 0 0 0-.7.7v12.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7H2.7zm7.43 0a.7.7 0 0 0-.7.7v12.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
            </svg>
          {:else}
            <svg viewBox="0 0 16 16" width="16" height="16" fill="black">
              <path d="M3 1.713a.7.7 0 0 1 1.05-.607l10.89 6.288a.7.7 0 0 1 0 1.212L4.05 14.894A.7.7 0 0 1 3 14.288V1.713z"></path>
            </svg>
          {/if}
        </button>
        {#if isSetMode}
          <button
            class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-muma-spotify-text {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
            onclick={() => skip(30)}
            disabled={transportLocked}
            aria-label={$t('player.skipForward')}
            title={$t('player.skipForward')}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
              <path d="M12 5V1l5 5-5 5V7a6 6 0 1 0 6 6h2a7 7 0 1 1-7-7z"></path>
            </svg>
            <span class="text-[8px] font-bold -ml-1">30</span>
          </button>
        {/if}
        <button
          class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-muma-spotify-text {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={playNext}
          disabled={transportLocked}
          aria-label={$t('player.next')}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M12.7 1a.7.7 0 0 0-.7.7v5.15L2.05 1.106A.7.7 0 0 0 1 1.712v12.575a.7.7 0 0 0 1.05.607L12 9.15v5.15a.7.7 0 0 0 .7.7h1.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7h-1.6z"></path>
          </svg>
        </button>
        <button class="hidden md:flex flex-col items-center relative bg-transparent border-none p-0 cursor-pointer transition-colors hover:text-white {repeatMode !== 'none' ? 'text-brand' : 'text-muma-spotify-text'}" onclick={toggleRepeat} aria-label={$t('player.repeat')}>
          <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
            <path d="M0 4.75A3.75 3.75 0 0 1 3.75 1h8.5A3.75 3.75 0 0 1 16 4.75v5a3.75 3.75 0 0 1-3.75 3.75H9.81l1.018 1.018a.75.75 0 1 1-1.06 1.06L6.939 12.75l2.829-2.828a.75.75 0 1 1 1.06 1.06L9.811 12h2.439a2.25 2.25 0 0 0 2.25-2.25v-5a2.25 2.25 0 0 0-2.25-2.25h-8.5A2.25 2.25 0 0 0 1.5 4.75v5A2.25 2.25 0 0 0 3.75 12H5v1.5H3.75A3.75 3.75 0 0 1 0 9.75v-5z"></path>
          </svg>
          {#if repeatMode === 'one'}
            <span class="absolute text-[7px] font-bold top-1/2 left-1/2 -translate-x-1/2 -translate-y-[60%] text-brand">1</span>
          {/if}
          {#if repeatMode !== 'none'}
            <div class="w-1 h-1 bg-brand rounded-full mt-0.5"></div>
          {/if}
        </button>
      </div>
      <div class="hidden md:flex w-full items-center gap-2 text-[11px] text-muma-spotify-text">
        <span>{isSetMode ? formatClock(progress) : formatTime(progress)}</span>
      {#if isSetMode}
        <!-- A native `range`, not the songs-mode click div below: a two-hour
             file needs real dragging, not a per-pixel click, to land on a
             chosen second -- see the "step 1 s" note in setResume.js's
             design. Arrow keys are overridden to ±30 s instead of the range's
             own 1 s step, matching the skip buttons above. -->
        <input
          type="range"
          class="flex-1 accent-brand-blue h-1 cursor-pointer {transportLocked ? 'pointer-events-none opacity-50' : ''}"
          min="0"
          max={duration || 0}
          step="1"
          value={progress}
          disabled={transportLocked}
          oninput={(e) => seekTo(Number(e.currentTarget.value))}
          onkeydown={(e) => {
            if (e.key === 'ArrowLeft') { e.preventDefault(); skip(-30); }
            else if (e.key === 'ArrowRight') { e.preventDefault(); skip(30); }
          }}
          aria-label={$t('player.seek')}
        />
      {:else}
        <div
          role="button"
          tabindex="0"
          class="flex-1 h-1 bg-[#4d4d4d] rounded-sm cursor-pointer {transportLocked ? 'pointer-events-none opacity-50' : ''}"
          onclick={seek}
          onkeydown={(e) => e.key === 'Enter' && seek(e)}
          aria-label={$t('player.seek')}
        >
          <div class="h-full bg-white rounded-sm" style="width: {progressPercent(progress, duration)}%"></div>
        </div>
      {/if}
        <span>{isSetMode ? formatClock(duration) : formatTime(duration)}</span>
      </div>
    </div>

    <div class="w-[30%] hidden md:flex justify-end items-center gap-3">
      {#if track}
        <div class="flex gap-0.5 mr-2">
          {#each [1, 2, 3, 4, 5] as star (star)}
            <button
              aria-label="{star} sterren"
              class="bg-transparent border-none p-0.5 cursor-pointer transition-colors { currentRating >= star ? 'text-brand' : 'text-white/10 hover:text-white/30' }"
              onclick={() => updateRating(star)}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
              </svg>
            </button>
          {/each}
        </div>
      {/if}
      <div class="relative flex items-center">
        <button
          class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white"
          style="color: {radioColor}"
          onclick={toggleRadio}
          title={isRadioActive ? 'Radio: aan het luisteren' : 'Radio (beta)'}
          aria-label={$t('player.radio')}
          aria-pressed={isRadioActive}
          aria-expanded={showRadioPicker}
        >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
              <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 4a6 6 0 1 1 0 12 6 6 0 0 1 0-12zm0 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />
            </svg>
        </button>
        {#if showRadioPicker}
          <div
            class="absolute bottom-full right-0 mb-3 w-56 bg-muma-spotify-light rounded-md shadow-xl border border-white/5 py-1 z-50"
            role="menu"
          >
            <div class="px-3 py-2 text-[10px] uppercase tracking-wider text-muma-spotify-text">
              {$t('radio.chooseChannel')}
            </div>
            {#each radioChannels as channel (channel.slug)}
              <button
                class="w-full text-left px-3 py-2 bg-transparent border-none cursor-pointer text-sm text-white hover:bg-white/10 transition-colors"
                role="menuitem"
                onclick={() => startRadio(channel)}
              >
                <span class="font-bold">{channel.name}</span>
                <span class="block text-[11px] text-muma-spotify-text">
                  {describeFilter(channel.filter, $t('management.radio.wholeLibrary'))}
                </span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
      <button
        class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white"
        style="color: {newsColor}"
        onclick={toggleNews}
        title={newsSnapshot ? $t('news.playing') : $t('news.play')}
        aria-label={$t('news.play')}
        aria-pressed={newsSnapshot !== null}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
          <path d="M20 3H4a2 2 0 0 0-2 2v12a3 3 0 0 0 3 3h14a3 3 0 0 0 3-3V5a2 2 0 0 0-2-2zM5 18a1 1 0 0 1-1-1V5h12v12a3 3 0 0 0 .17 1zm14 0a1 1 0 0 1-1-1V5h2v12a1 1 0 0 1-1 1zM6 7h8v2H6zm0 4h8v2H6zm0 4h5v2H6z" />
        </svg>
      </button>
      <button
        class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors"
        onclick={toggleJamMode}
        title={syncTitle}
        style="color: {syncColor}"
      >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-5.5-8c0 3.03 2.47 5.5 5.5 5.5s5.5-2.47 5.5-5.5-2.47-5.5-5.5-5.5-5.5 2.47-5.5 5.5z"></path>
          </svg>
      </button>
      {#if equalizerSupported}
        <div class="relative">
          <button
            data-eq-toggle
            class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white {$equalizerSettings.enabled ? 'text-brand' : 'text-muma-spotify-text'}"
            onclick={() => (showEqualizer = !showEqualizer)}
            aria-label={$t('equalizer.title')}
            aria-pressed={showEqualizer}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M4 20V14M4 10V4M12 20V12M12 8V4M20 20V16M20 12V4M1 14h6M9 8h6M17 16h6"></path>
            </svg>
          </button>
          {#if showEqualizer}
            <div bind:this={equalizerPanelEl} class="absolute bottom-full right-0 mb-3 z-50">
              <Equalizer onclose={() => (showEqualizer = false)} />
            </div>
          {/if}
        </div>
      {/if}
      {#if lyricsLines.length > 0}
        <div class="relative">
          <button
            class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white {showLyricsPanel ? 'text-brand' : 'text-muma-spotify-text'}"
            onclick={() => (showLyricsPanel = !showLyricsPanel)}
            aria-label={$t('track.lyrics')}
            aria-pressed={showLyricsPanel}
            aria-expanded={showLyricsPanel}
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true">
              <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"></path>
            </svg>
          </button>
          {#if showLyricsPanel}
            <div
              class="absolute bottom-full right-0 mb-3 w-64 max-h-72 overflow-y-auto bg-muma-spotify-light rounded-md shadow-xl border border-white/5 p-3 z-50 text-sm text-white"
              role="dialog"
              aria-label={$t('track.lyrics')}
            >
              {#each lyricsLines as line, i (i)}
                <p class="m-0 mb-1 last:mb-0">{line}</p>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
      <button class="mr-2 bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-muma-spotify-text" onclick={ontoggleQueue} aria-label={$t('queue.title')}>
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <path d="M15 15H3v-1.5h12V15zm0-4.5H3V9h12v1.5zm0-4.5H3V4.5h12V6zm7 12l-4.5-4.5L13 18h9z"></path>
          </svg>
      </button>
      <button class="bg-transparent border-none p-0 flex items-center justify-center cursor-pointer transition-colors hover:text-white text-muma-spotify-text" onclick={toggleMute}>
          {#if muted || volume === 0}
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M16.107 2.493a.75.75 0 0 0-1.06 0l-7.057 7.057H2.25a.75.75 0 0 0-.75.75v3.314a.75.75 0 0 0 .75.75h5.74l7.057 7.057a.75.75 0 0 0 1.28-.53V3.023a.75.75 0 0 0-.22-.53zM14.607 18.66l-5.914-5.914a.75.75 0 0 0-.53-.22H3v-1.814h5.163a.75.75 0 0 0 .53-.22l5.914-5.914V18.66z"></path>
              </svg>
          {:else}
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M15.545 1.488a.75.75 0 0 1 .103 1.055C18.106 5.54 19.5 9.1 19.5 13s-1.394 7.46-3.852 10.457a.75.75 0 1 1-1.154-.959C16.634 19.863 18 16.594 18 13c0-3.594-1.366-6.863-3.507-9.458a.75.75 0 0 1 .103-1.054zm-2.81 3.23a.75.75 0 0 1 .102 1.054C14.346 7.41 15 10.124 15 13c0 2.876-.654 5.59-2.163 7.228a.75.75 0 1 1-1.155-.958C13.065 17.518 13.5 15.308 13.5 13c0-2.308-.435-4.518-1.838-6.228a.75.75 0 0 1 .103-1.054zM9.548 8.016a.75.75 0 0 1 .103 1.054C10.222 9.8 10.5 11.371 10.5 13c0 1.629-.278 3.2-.849 3.93a.75.75 0 1 1-1.155-.958c.321-.386.504-1.516.504-2.972 0-1.456-.183-2.586-.504-2.972a.75.75 0 0 1 .103-1.054z"></path>
              </svg>
          {/if}
      </button>
      <div
        role="button"
        tabindex="0"
        class="w-24 h-1 bg-[#4d4d4d] rounded-sm cursor-pointer"
        onclick={changeVolume}
        onwheel={(e) => {
          if (e.deltaY > 0) volumeDown();
          else volumeUp();
        }}
        onkeydown={(e) => e.key === 'Enter' && changeVolume(e)}
        aria-label={$t('player.volume')}
      >
        <div class="h-full bg-white rounded-sm" style="width: {volume}%"></div>
      </div>
    </div>
  {/if}

  {#if track && releaseDate}
    <div class="hidden md:block absolute bottom-1 right-4 text-[10px] text-white/30 pointer-events-none select-none">
      {releaseDate}
    </div>
  {/if}
</footer>

<style>
</style>
