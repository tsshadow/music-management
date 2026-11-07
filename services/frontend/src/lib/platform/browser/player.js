import { audio } from "../../store.js";
import * as equalizer from "../../equalizer.js";
import { resolveDuration } from "../../playerProgress.js";

/**
 * The browser playback engine: everything `Player.svelte` used to do with its
 * `<audio>` element, behind the `platform.player` interface documented in
 * `../index.js`.
 *
 * The element itself is still rendered by `Player.svelte` and handed over with
 * `attach()`. That is deliberate: the element needs `crossorigin="anonymous"`
 * from its first byte for the Web Audio equalizer to be allowed to read it, and
 * a component-owned element keeps the DOM exactly as it was. A native
 * implementation ignores `attach()` altogether -- there, the platform service
 * owns the engine and no `<audio>` element exists at all.
 *
 * Nothing here knows about the queue, radio, the news, jam sync or shuffle;
 * those stay in `Player.svelte`, which drives this engine.
 */

/**
 * The events an engine emits. Keep in sync with the JSDoc in `../index.js`.
 *
 * `command` is in the list and never fires here: it reports a transport move a
 * platform service performed by itself, and in a tab there is no such service.
 * Accepting the subscription is what lets `Player.svelte` take it out
 * unconditionally instead of asking which shell it is running in.
 */
const EVENTS = [
  "timeupdate",
  "durationchange",
  "play",
  "pause",
  "ended",
  "error",
  "volumechange",
  "buffering",
  "command",
];

/**
 * `HTMLMediaElement.HAVE_FUTURE_DATA`: from this ready state on, the element has
 * enough data to move the position forward. Below it, a play request waits.
 */
const HAVE_FUTURE_DATA = 3;

/** What a queue-less engine answers with. See `ownsQueue` in `../index.js`. */
const NO_QUEUE = Object.freeze({ index: -1, length: 0, trackIds: [] });

/** The snapshot an engine that has nothing to play reports. */
const EMPTY_STATE = Object.freeze({
  status: "idle",
  position: 0,
  duration: 0,
  trackId: null,
  volume: 1,
  buffering: false,
});

function hasMediaSession() {
  return typeof navigator !== "undefined" && "mediaSession" in navigator;
}

/**
 * Builds one playback engine.
 *
 * Exported for the tests, which need an engine of their own rather than the
 * module-level one the app shares; the app itself imports the default export.
 *
 * @returns {object} An implementation of the `platform.player` interface.
 */
export function createBrowserPlayer() {
  /** @type {HTMLMediaElement|null} */
  let media = null;
  /** @type {Array<[string, EventListener]>} */
  let domListeners = [];
  /** @type {Map<string, Set<Function>>} */
  const subscribers = new Map(EVENTS.map((name) => [name, new Set()]));

  let trackId = null;
  let hasSource = false;
  let errored = false;
  /** True while a play request waits for data. See `setBuffering`. */
  let buffering = false;
  /** @type {ReturnType<typeof setInterval>|null} */
  let ticker = null;
  /** @type {object|null} */
  let nowPlaying = null;
  /** @type {object} */
  let commands = {};

  function emit(event) {
    const snapshot = state();
    for (const handler of subscribers.get(event) ?? []) {
      handler(snapshot);
    }
  }

  /**
   * The length the engine measured itself, or 0 when it has none.
   *
   * `HTMLMediaElement.duration` is `NaN` before the metadata lands and
   * `Infinity` for a chunked transcode; both mean "no length", and callers get
   * 0 so they can fall back to what the library reported.
   */
  function measuredDuration() {
    const value = media?.duration;
    return Number.isFinite(value) && value > 0 ? value : 0;
  }

  /** Measured length, or the one the caller last reported in `setNowPlaying`. */
  function playableLength() {
    return resolveDuration(measuredDuration(), nowPlaying?.duration ?? 0);
  }

  function status() {
    if (!media || !hasSource) return "idle";
    // Before everything else, so "playing" always means exactly
    // `!element.paused` -- which is what every caller used to read.
    if (!media.paused) return "playing";
    if (errored) return "error";
    if (media.ended) return "ended";
    if (media.readyState === 0) return "loading";
    return "paused";
  }

  /** @returns {{status: string, position: number, duration: number, trackId: string|null, volume: number, buffering: boolean}} */
  function state() {
    if (!media) return { ...EMPTY_STATE };
    return {
      status: status(),
      position: media.currentTime || 0,
      duration: measuredDuration(),
      trackId,
      volume: media.volume,
      buffering,
    };
  }

  /**
   * Records whether a play request waits for data, and emits `buffering` when
   * that changes.
   *
   * The status stays `playing` while the element waits: it is not paused, and
   * the play button still has to pause it. This flag is what tells the button
   * to show a throbber in place of the pause icon.
   *
   * @param {boolean} value
   */
  function setBuffering(value) {
    if (buffering === value) return;
    buffering = value;
    emit("buffering");
  }

  /**
   * Tells the OS where playback is, so a notification, a lock screen or a car
   * head unit can draw its own progress bar.
   */
  function updatePositionState() {
    if (!media || !hasMediaSession() || !("setPositionState" in navigator.mediaSession)) return;
    const length = playableLength();
    if (length <= 0) return;
    try {
      navigator.mediaSession.setPositionState({
        duration: length,
        playbackRate: media.playbackRate || 1,
        position: Math.max(0, Math.min(media.currentTime || 0, length)),
      });
    } catch (e) {
      console.error("Failed to set position state", e);
    }
  }

  function setPlaybackState(value) {
    if (hasMediaSession()) navigator.mediaSession.playbackState = value;
  }

  function tick() {
    updatePositionState();
    emit("timeupdate");
  }

  /**
   * Polls the element while it plays.
   *
   * The `timeupdate` event is the obvious source for the position, and on a
   * desktop browser it is enough. The LG TV browser only fires it on a state
   * change -- play, pause, seek, ended -- and never on the ~4Hz cadence the
   * spec asks for, so a progress bar there sits still until someone touches the
   * transport. Reading `currentTime` on a timer of our own is the same number
   * from the same element and costs nothing, so it drives the bar everywhere
   * rather than only on the devices that misbehave.
   */
  function startTicker() {
    stopTicker();
    ticker = setInterval(() => {
      if (status() === "playing") tick();
    }, 250);
  }

  function stopTicker() {
    if (ticker) {
      clearInterval(ticker);
      ticker = null;
    }
  }

  function wire() {
    const on = (name, handler) => {
      media.addEventListener(name, handler);
      domListeners.push([name, handler]);
    };
    on("timeupdate", tick);
    on("loadedmetadata", () => {
      updatePositionState();
      emit("durationchange");
    });
    // `waiting` fires when a play request runs out of data: at the start of a
    // new source, after a seek into a part not loaded yet, or when the network
    // falls behind. `stalled` only says the download stopped; with enough data
    // buffered the element plays on, so it counts only below HAVE_FUTURE_DATA.
    on("waiting", () => setBuffering(true));
    on("stalled", () => {
      if (!media.paused && media.readyState < HAVE_FUTURE_DATA) setBuffering(true);
    });
    on("playing", () => setBuffering(false));
    on("canplay", () => setBuffering(false));
    on("canplaythrough", () => setBuffering(false));
    on("emptied", () => setBuffering(false));
    on("play", () => {
      // A context the browser suspended passes no sound at all, and play is the
      // moment that matters.
      equalizer.resume();
      setPlaybackState("playing");
      startTicker();
      emit("play");
    });
    on("pause", () => {
      setBuffering(false);
      setPlaybackState("paused");
      // The element fires its own `timeupdate` on a pause -- on every browser,
      // the TV included -- so the final position lands without a tick.
      stopTicker();
      emit("pause");
    });
    on("ended", () => {
      setBuffering(false);
      stopTicker();
      emit("ended");
    });
    on("error", () => {
      errored = true;
      setBuffering(false);
      emit("error");
    });
    on("volumechange", () => emit("volumechange"));
  }

  function unwire() {
    stopTicker();
    for (const [name, handler] of domListeners) media?.removeEventListener(name, handler);
    domListeners = [];
  }

  /**
   * Hands the engine the element it drives.
   *
   * @param {HTMLMediaElement|null} element
   */
  function attach(element) {
    if (media === element) return;
    unwire();
    media = element ?? null;
    trackId = null;
    hasSource = false;
    errored = false;
    buffering = false;
    // Other modules read the element from this store; it is the engine that
    // owns it, so it is the engine that publishes it.
    audio.set(media);
    if (media) wire();
  }

  function detach() {
    unwire();
    media = null;
    trackId = null;
    hasSource = false;
    errored = false;
    buffering = false;
    audio.set(null);
  }

  /** True once the engine has something to drive. */
  function ready() {
    return media !== null;
  }

  /**
   * Points the engine at something to play.
   *
   * @param {{url: string, trackId?: string|null, position?: number, autoplay?: boolean}} request
   * @returns {Promise<void>}
   */
  async function load({ url, trackId: id = null, position = 0, autoplay = false } = {}) {
    if (!media || !url) return;
    errored = false;
    // A new source starts unbuffered. The element fires `waiting` by itself
    // once a play request finds no data, so nothing is set here.
    setBuffering(false);
    trackId = id;
    media.src = url;
    hasSource = true;
    if (position) media.currentTime = position;
    if (autoplay) await media.play();
  }

  /** @returns {Promise<void>} */
  function play() {
    if (!media) return Promise.resolve();
    return media.play() ?? Promise.resolve();
  }

  function pause() {
    media?.pause();
  }

  /** Stops and lets go of the source, leaving the engine idle. */
  function stop() {
    if (!media) return;
    stopTicker();
    media.pause();
    media.removeAttribute("src");
    hasSource = false;
    trackId = null;
    errored = false;
    setBuffering(false);
  }

  /**
   * Native-only on the capacitor engine, where the platform service holds the queue and has to be
   * asked to move it. A browser tab's queue lives in `Player.svelte`, which already advances it
   * itself and never calls this -- kept here only so a caller that branches on `platform.system.isNative`
   * rather than on `ownsQueue` still finds a function rather than `undefined`.
   */
  function next() {}

  /** See `next`. */
  function previous() {}

  /** @param {number} seconds */
  function seek(seconds) {
    if (media) media.currentTime = seconds;
  }

  /** @param {number} value - 0..1 */
  function setVolume(value) {
    if (media) media.volume = Math.max(0, Math.min(1, value));
  }

  /** @param {number} value - 1 is normal speed. */
  function setRate(value) {
    if (media) media.playbackRate = value;
  }

  /**
   * The one place equalizer settings reach the audio graph. Attaching happens
   * lazily, on the first switch-on: that is always a user gesture, which is what
   * the browser demands before an AudioContext may start.
   *
   * @param {{enabled: boolean, gains: number[], preamp: number}} settings
   * @returns {boolean} whether the curve is in effect.
   */
  function setEqualizer(settings) {
    if (!settings?.enabled) {
      equalizer.setEnabled(false);
      return false;
    }
    if (!equalizer.attach(media)) return false;
    equalizer.setGains(settings.gains);
    equalizer.setPreamp(settings.preamp);
    equalizer.setEnabled(true);
    return true;
  }

  /**
   * What the OS shows for the current item.
   *
   * @param {{title?: string, artist?: string, album?: string, artworkUrl?: string,
   *          duration?: number}|null} metadata
   */
  function setNowPlaying(metadata) {
    nowPlaying = metadata ?? null;
    if (!hasMediaSession()) return;
    if (!metadata) {
      navigator.mediaSession.metadata = null;
      return;
    }
    navigator.mediaSession.metadata = new MediaMetadata({
      title: metadata.title,
      artist: metadata.artist,
      album: metadata.album,
      artwork: metadata.artworkUrl
        ? [{ src: metadata.artworkUrl, sizes: "512x512", type: "image/jpeg" }]
        : [],
    });
    updatePositionState();
  }

  /**
   * What a transport control outside the app does. In the browser these are the
   * Media Session action handlers -- keyboard media keys, the lock screen, a
   * Bluetooth remote.
   *
   * @param {{play?: Function, pause?: Function, next?: Function, previous?: Function,
   *          seekTo?: function(number): void}} handlers
   */
  function setCommandHandlers(handlers) {
    commands = handlers ?? {};
    if (!hasMediaSession()) return;
    const set = (action, handler) => {
      try {
        navigator.mediaSession.setActionHandler(action, handler ?? null);
      } catch (e) {
        // The action goes in as an argument rather than into the string: a
        // template literal in a log call is a format-string finding, and the
        // console prints it just the same.
        console.warn("MediaSession action not supported", action, e);
      }
    };
    set("play", commands.play && (() => commands.play()));
    set("pause", commands.pause && (() => commands.pause()));
    set("previoustrack", commands.previous && (() => commands.previous()));
    set("nexttrack", commands.next && (() => commands.next()));
    set(
      "seekto",
      commands.seekTo &&
        ((details) => {
          if (details?.seekTime !== undefined) commands.seekTo(details.seekTime);
        }),
    );
  }

  /**
   * @param {string} event
   * @param {function(object): void} handler
   * @returns {function(): void} Unsubscribes.
   */
  function on(event, handler) {
    const set = subscribers.get(event);
    if (!set) throw new Error(`Unknown player event: ${event}`);
    set.add(handler);
    return () => set.delete(handler);
  }

  /**
   * The element being driven, for the few modules that still speak to it
   * directly (the radio controller). Browser only; a native engine returns null.
   *
   * @returns {HTMLMediaElement|null}
   */
  function element() {
    return media;
  }

  /**
   * The queue is the UI's here, so there is nothing to hand over and nothing to
   * read back. Both answer with an empty queue rather than throwing, so the
   * queue logic can call them without first asking which shell it is in; the
   * `ownsQueue` flag is what it branches on when the answer actually matters.
   *
   * @returns {Promise<{index: number, length: number, trackIds: string[]}>}
   */
  async function setQueue() {
    return { ...NO_QUEUE };
  }

  /** @returns {Promise<{index: number, length: number, trackIds: string[]}>} */
  async function queueState() {
    return { ...NO_QUEUE };
  }

  /**
   * Deliberately does nothing beyond answering.
   *
   * Shuffle and repeat stay a decision `Player.svelte` makes for itself when `ownsQueue` is
   * false -- there is no service on this side of the bridge for either to live on, and the
   * contract says the fields are simply absent from a browser's state. Answering with the
   * unchanged snapshot is what lets a caller invoke this unconditionally rather than asking
   * which shell it is in first, the same as `setQueue`/`queueState` above.
   *
   * @returns {Promise<object>}
   */
  async function setMode() {
    return state();
  }

  /**
   * Deliberately does nothing.
   *
   * Radio and the news are driven directly by `Player.svelte` here -- `radioController.js` steers
   * this same element, and a bulletin plays from a blob URL on it -- so neither of these three is
   * ever actually called in a browser tab. They exist so the contract answers every call the same
   * way `setQueue`/`setMode` already do, without a caller having to ask which shell it is in first.
   */
  async function startRadio() {}

  /** @see startRadio */
  async function setFavoriteStations() {}

  /** @see startRadio */
  async function startStation() {}

  /** @see startRadio */
  async function stopRadio() {}

  /** @see startRadio */
  async function toggleNews() {}

  return {
    ownsQueue: false,
    setQueue,
    queueState,
    setMode,
    startRadio,
    setFavoriteStations,
    startStation,
    stopRadio,
    toggleNews,
    attach,
    detach,
    ready,
    load,
    play,
    pause,
    stop,
    next,
    previous,
    seek,
    setVolume,
    setRate,
    setEqualizer,
    setNowPlaying,
    setCommandHandlers,
    on,
    state,
    element,
  };
}

/** The engine the app shares. One page, one playback engine. */
export default createBrowserPlayer();
