import { listen, fireAndForget } from "./listen.js";

/**
 * `platform.player` inside the Android shell: a thin proxy over the
 * `MumaPlayer` Kotlin plugin, which drives `PlaybackService` -- the same
 * ExoPlayer session that owns the notification, the lock screen, Bluetooth and
 * Android Auto.
 *
 * Two things about this implementation are worth stating before reading it.
 *
 * **It never plays anything itself.** No `<audio>` element is created, none is
 * attached, and `load()` ignores the `url` the browser engine needs: the
 * service resolves a downloaded file or a stream URL on its own. Two engines
 * alive at once is the failure this whole design is arranged to prevent.
 *
 * **`state()` is synchronous, and the bridge is not.** Every caller in the web
 * module reads `platform.player.state().position` inline -- in a progress bar,
 * in a scrobble, in the jam sync loop -- and a promise there would be a rewrite
 * of all of them for no gain. So the snapshot is cached: every event the plugin
 * sends carries the full state, `timeupdate` arrives four times a second while
 * playing, and `refresh()` pulls one on demand (the boot path uses it). What
 * `state()` returns is therefore the last thing the service said, which is what
 * the browser engine's `state()` is as well -- it reads an element that was
 * last updated by an event too.
 */

/** The events a `platform.player` emits, plus the one only a native queue has. */
const EVENTS = [
  "timeupdate",
  "durationchange",
  "play",
  "pause",
  "ended",
  "error",
  "volumechange",
  // Native only: the service moved the transport and the UI has to follow. See
  // `on()` below for why this is not `setCommandHandlers`.
  "command",
];

/** The snapshot before the plugin has said anything. */
const EMPTY_STATE = Object.freeze({
  status: "idle",
  position: 0,
  duration: 0,
  trackId: null,
  volume: 1,
  queueIndex: -1,
  queueLength: 0,
  shuffle: false,
  repeat: "none",
  radioChannel: null,
  newsPlaying: false,
});

/** The three words `setMode`'s `repeat` and `state().repeat` are allowed to answer with. */
const REPEAT_MODES = new Set(["none", "all", "one"]);

/** An empty queue, in the shape `setQueue`/`queueState` answer with. */
const EMPTY_QUEUE = Object.freeze({ index: -1, length: 0, trackIds: [] });

function numberOr(value, fallback) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/**
 * Normalises what the plugin answered into the contract's snapshot.
 *
 * Every field is defended: a bridge message is JSON from another process, and a
 * missing `position` must read as "where it was", not as `NaN` in a progress
 * bar.
 *
 * @param {object|null} payload
 * @param {object} previous
 * @returns {object}
 */
function snapshotOf(payload, previous) {
  if (!payload || typeof payload !== "object") return previous;
  return {
    status: typeof payload.status === "string" ? payload.status : previous.status,
    position: numberOr(payload.position, previous.position),
    duration: numberOr(payload.duration, previous.duration),
    trackId: payload.trackId == null ? null : String(payload.trackId),
    volume: numberOr(payload.volume, previous.volume),
    queueIndex: numberOr(payload.queueIndex, previous.queueIndex),
    queueLength: numberOr(payload.queueLength, previous.queueLength),
    shuffle: typeof payload.shuffle === "boolean" ? payload.shuffle : previous.shuffle,
    repeat: REPEAT_MODES.has(payload.repeat) ? payload.repeat : previous.repeat,
    radioChannel: payload.radioChannel == null ? null : String(payload.radioChannel),
    newsPlaying: payload.newsPlaying === true,
  };
}

/**
 * Normalises a queue answer.
 *
 * @param {object|null} payload
 * @returns {{index: number, length: number, trackIds: string[]}}
 */
function queueOf(payload) {
  if (!payload || typeof payload !== "object") return { ...EMPTY_QUEUE };
  const trackIds = Array.isArray(payload.trackIds) ? payload.trackIds.map(String) : [];
  return {
    index: numberOr(payload.index, -1),
    length: numberOr(payload.length, trackIds.length),
    trackIds,
  };
}

/**
 * Builds the native playback engine.
 *
 * @param {object} plugin - The registered `MumaPlayer` plugin, injected so the
 *   tests can hand in a fake whose listeners they can fire themselves.
 * @returns {object} An implementation of the `platform.player` interface.
 */
export function createCapacitorPlayer(plugin) {
  /** @type {Map<string, Set<Function>>} */
  const subscribers = new Map(EVENTS.map((name) => [name, new Set()]));
  let snapshot = { ...EMPTY_STATE };
  let equalizerInEffect = false;

  /** Subscribed once, here, rather than per `on()` call: the cache has to stay
   *  warm even while no screen is listening, because `state()` is read inline. */
  for (const event of EVENTS) {
    if (event === "command") continue;
    listen(plugin, event, (payload) => {
      snapshot = snapshotOf(payload, snapshot);
      emit(event, { ...snapshot, ...extrasOf(event, payload) });
    });
  }
  listen(plugin, "command", (payload) => {
    emit("command", {
      name: String(payload?.name ?? ""),
      seconds: typeof payload?.seconds === "number" ? payload.seconds : null,
      state: { ...snapshot },
    });
  });

  /** `error` carries a reason alongside the snapshot; nothing else adds fields. */
  function extrasOf(event, payload) {
    if (event !== "error") return {};
    return { code: payload?.code ?? null, message: payload?.message ?? "" };
  }

  function emit(event, value) {
    for (const handler of subscribers.get(event) ?? []) {
      try {
        handler(value);
      } catch (error) {
        console.error("A player event handler failed", event, error);
      }
    }
  }

  /**
   * Pulls a fresh snapshot across the bridge.
   *
   * The boot path calls this: after the WebView was reclaimed the service kept
   * playing, and the first thing a rebuilt UI needs is where it got to.
   *
   * @returns {Promise<object>} The snapshot, also cached for `state()`.
   */
  async function refresh() {
    try {
      snapshot = snapshotOf(await plugin.state(), snapshot);
    } catch (error) {
      console.warn("Could not read the native player state", error);
    }
    return { ...snapshot };
  }

  return {
    /**
     * True here and false in the browser: the service holds the queue, so the
     * UI pushes it across and mirrors what comes back instead of advancing by
     * itself. Every place that behaves differently on a native shell branches
     * on this one flag.
     */
    ownsQueue: true,

    /** Browser-only. There is no element to hand over and none is made. */
    attach() {},

    /**
     * Browser-only. Deliberately not "unsubscribe from the plugin": the engine
     * outlives any one component, and a remount would have no way to get its
     * events back. Subscriptions taken through `on()` are undone by the
     * functions it returned.
     */
    detach() {},

    /** The service is there from process start; there is nothing to wait for. */
    ready() {
      return true;
    },

    /**
     * @param {{url?: string, trackId?: string|null, position?: number, autoplay?: boolean}} request
     *   `url` is accepted and ignored -- the caller builds one for the browser
     *   engine and it costs nothing to let it. The service resolves the source.
     * @returns {Promise<void>}
     */
    async load({ trackId = null, position = 0, autoplay = false } = {}) {
      if (trackId == null) return;
      await plugin.load({ trackId: String(trackId), position, autoplay });
    },

    /**
     * Replaces the service's queue wholesale.
     *
     * @param {{tracks: Array<object>, index?: number, autoplay?: boolean}} request
     * @returns {Promise<{index: number, length: number, trackIds: string[]}>}
     */
    async setQueue({ tracks = [], index = 0, autoplay = false } = {}) {
      return queueOf(await plugin.setQueue({ tracks, index, autoplay }));
    },

    /** @returns {Promise<{index: number, length: number, trackIds: string[]}>} */
    async queueState() {
      try {
        return queueOf(await plugin.queueState());
      } catch (error) {
        console.warn("Could not read the native queue", error);
        return { ...EMPTY_QUEUE };
      }
    },

    /** @returns {Promise<void>} */
    async play() {
      await plugin.play();
    },

    pause() {
      fireAndForget("pause", plugin.pause());
    },

    stop() {
      fireAndForget("stop", plugin.stop());
    },

    /**
     * Moves the service's queue forward one track. Native only -- there is no equivalent on the
     * browser engine, whose queue lives in `Player.svelte` -- so this exists for screens that are
     * themselves native-only, today just the car-mode screen. Nothing here mirrors the move into
     * `state()`/`currentTrack` by itself: the plugin call changes the service's queue index, which
     * the existing `tick()` polling on the Kotlin side already reports as a `command` event no
     * differently than a head-unit button press, and the same `on('command', ...)` handling that
     * already exists for that case is what draws the new track.
     */
    next() {
      fireAndForget("next", plugin.next());
    },

    /** See `next`. */
    previous() {
      fireAndForget("previous", plugin.previous());
    },

    /** @param {number} seconds */
    seek(seconds) {
      fireAndForget("seek", plugin.seek({ seconds }));
    },

    /** @param {number} value - 0..1 */
    setVolume(value) {
      fireAndForget("setVolume", plugin.setVolume({ value: Math.max(0, Math.min(1, value)) }));
    },

    /** @param {number} value - 1 is normal speed. */
    setRate(value) {
      fireAndForget("setRate", plugin.setRate({ value }));
    },

    /**
     * Puts shuffle and repeat on the service, which is where they have to live once it owns the
     * queue: Media3 already applies both when the current item ends or a head unit asks for
     * "next", with no JS in the loop at all. The snapshot the plugin answers with is cached the
     * same way every other event does, so the very next `state()` read -- and the caller that
     * awaited this -- see the mode that was actually applied rather than the one that was asked
     * for.
     *
     * @param {{shuffle: boolean, repeat: 'none'|'all'|'one'}} mode
     * @returns {Promise<object>}
     */
    async setMode({ shuffle = false, repeat = "none" } = {}) {
      snapshot = snapshotOf(await plugin.setMode({ shuffle, repeat }), snapshot);
      return { ...snapshot };
    },

    /**
     * Hands the curve to the platform equalizer that sits on the ExoPlayer
     * session, not to a Web Audio graph -- there is no element to build one
     * around.
     *
     * The contract's return value is synchronous, and the bridge is not, so
     * this answers with the last thing the plugin said and updates that when
     * the call lands. The only caller reads it to draw a state that the next
     * change corrects anyway.
     *
     * @param {{enabled: boolean, gains: number[], preamp: number}} settings
     * @returns {boolean} Whether the curve was in effect as of the last answer.
     */
    setEqualizer(settings) {
      const request = {
        enabled: settings?.enabled === true,
        gains: settings?.gains ?? [],
        preamp: settings?.preamp ?? 0,
      };
      Promise.resolve(plugin.setEqualizer(request))
        .then((answer) => {
          equalizerInEffect = answer?.value === true;
        })
        .catch((error) => console.warn("Could not apply the equalizer", error));
      return equalizerInEffect;
    },

    /**
     * Tunes into a channel by slug. The service streams it and locks onto the server's timeline
     * itself -- [RadioPlaybackController.kt]/[RadioSync.kt], reused from Android Auto's own radio
     * support rather than a second copy of the maths living here too.
     *
     * @param {string} slug
     * @returns {Promise<void>}
     */
    async startRadio(slug) {
      await plugin.startRadio({ slug });
    },

    /** Leaves radio mode without starting anything else. */
    async stopRadio() {
      await plugin.stopRadio();
    },

    /**
     * Plays the latest bulletin, or hands the music back if one is already running -- one call
     * either way, the same toggle the notification's own news button performs.
     *
     * @returns {Promise<void>}
     */
    async toggleNews() {
      await plugin.toggleNews();
    },

    /**
     * A no-op on the far side, and called anyway.
     *
     * The `MediaSession` derives the notification from the queue it was handed,
     * so there is exactly one source of truth for what is playing. The call is
     * kept because the contract has it and because a shell that ever grows a
     * second metadata source should find the seam here rather than in a screen.
     *
     * @param {object|null} metadata
     */
    setNowPlaying(metadata) {
      fireAndForget("setNowPlaying", plugin.setNowPlaying(metadata ?? {}));
    },

    /**
     * Deliberately does nothing.
     *
     * In the browser these are the Media Session handlers, and they come back
     * into the UI because the UI holds the queue. Here the service holds it: a
     * "next" from the head unit is performed by the service and reported back
     * as a `command` event, which the UI follows. Calling the handler as well
     * would make the UI ask for a move that already happened.
     */
    setCommandHandlers() {},

    /**
     * @param {string} event
     * @param {function(object): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    on(event, handler) {
      const set = subscribers.get(event);
      if (!set) throw new Error(`Unknown player event: ${event}`);
      set.add(handler);
      return () => set.delete(handler);
    },

    /** The last snapshot the service sent or `refresh()` pulled. */
    state() {
      return { ...snapshot };
    },

    refresh,

    /** Browser-only; there is no media element in this shell. */
    element() {
      return null;
    },
  };
}
