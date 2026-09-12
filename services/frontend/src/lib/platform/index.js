import browserPlayer from "./browser/player.js";
import browserStorage from "./browser/storage.js";
import browserSpeech from "./browser/speech.js";
import browserDiagnostics from "./browser/diagnostics.js";
import browserSystem from "./browser/system.js";
import { createCapacitorPlatform } from "./capacitor/index.js";

/**
 * Everything the UI is not allowed to know by itself.
 *
 * One interface, one implementation per shell. The screens, the stores and the
 * router import `platform` and nothing else platform-specific; playback,
 * offline storage, voice, diagnostics and the shell's own events all arrive
 * through here. Today there is exactly one implementation, the browser one --
 * which is what `Player.svelte` used to do inline -- and the selection below
 * falls through to it. A Capacitor shell plugs its Kotlin plugins in at that one
 * spot, and a desktop shell later does the same.
 *
 * The interface below is a contract between two codebases, so it is written out
 * rather than left to be read off the browser implementation: method names,
 * argument shapes, event names and the state snapshot are what a plugin has to
 * answer with, and changing one of them is a change on both sides.
 *
 * Rules that hold for every implementation:
 *
 * - Every `on*` subscription returns a function that unsubscribes.
 * - A subscription may fire immediately on subscribe if it has a current value;
 *   nothing may assume it will.
 * - Anything that can fail returns a promise and rejects with an `Error`.
 * - A capability that is missing reports `supported: false` and still answers
 *   every call, with the emptiest honest value. Screens hide themselves on the
 *   flag; they must not have to catch exceptions to find out.
 * - Nothing here knows about the queue, shuffle, radio, jam sync or the news.
 *   Those are UI state, they live in the web module, and they drive `player`.
 */

/**
 * @typedef {'idle'|'loading'|'playing'|'paused'|'ended'|'error'} PlayerStatus
 *   `idle` nothing loaded · `loading` a source is set but not yet playable ·
 *   `playing` exactly when the engine is not paused · `paused` · `ended` the
 *   source ran out · `error` the source failed.
 */

/**
 * @typedef {object} PlayerState The whole of what the engine knows, in one
 *   snapshot. Read with `player.state()`; passed to every event handler.
 * @property {PlayerStatus} status
 * @property {number} position Seconds into the current item.
 * @property {number} duration Seconds, as the engine measured it, or 0 when it
 *   has no length of its own -- a chunked transcode has none. Callers fall back
 *   to the length the library reported; `playerProgress.resolveDuration` is that
 *   fallback.
 * @property {string|null} trackId The id passed to `load()`, or null.
 * @property {number} volume 0..1.
 */

/**
 * @typedef {'timeupdate'|'durationchange'|'play'|'pause'|'ended'|'error'|'volumechange'|'command'} PlayerEvent
 *   `timeupdate` position moved (at least four times a second while playing) ·
 *   `durationchange` a length is known for the loaded item · `play` · `pause` ·
 *   `ended` the item ran out, which is the cue to advance the queue · `error`
 *   the source failed · `volumechange`. Every handler is called with the
 *   {@link PlayerState} snapshot as it is after the event.
 *
 *   `command` is the exception, and only an implementation with `ownsQueue`
 *   sends it: `{name: 'next'|'previous'|'play'|'pause'|'seekTo', seconds, state}`
 *   reports a transport move the platform service *already performed* -- from
 *   the notification, a head unit, a headset button, or the end of a track. The
 *   UI mirrors it into its own state; it must not perform the move again. A
 *   browser tab accepts the subscription and never fires it, so a caller needs
 *   no branch around it.
 */

/**
 * @typedef {object} PlatformPlayer One playback engine. Never two at once: on a
 *   native shell the platform service owns playback and no `<audio>` element is
 *   created at all.
 * @property {boolean} ownsQueue Whether the queue lives on the far side. False
 *   in a browser: the UI holds the list, advances it on `ended`, and the engine
 *   only ever knows about one source at a time. True on a shell whose service
 *   survives the UI -- there the whole list goes across with `setQueue`, the
 *   service decides what plays next, `ended` must not advance anything in JS,
 *   and `command` events are what the UI follows. Everything that has to behave
 *   differently branches on this one flag.
 * @property {function({tracks: Array<object>, index?: number, autoplay?: boolean}):
 *   Promise<{index: number, length: number, trackIds: string[]}>} setQueue
 *   Replaces the platform queue wholesale; the order of `tracks` is the order
 *   of the queue. Each track is `{id, title, artist, album, artworkUrl,
 *   duration}`. A browser answers with an empty queue and keeps its own list,
 *   so the UI can call this unconditionally.
 * @property {function(): Promise<{index: number, length: number, trackIds: string[]}>} queueState
 *   What the platform is holding. This is what a UI rebuilt after the WebView
 *   died reads to find its way back.
 * @property {function(HTMLMediaElement|null): void} attach Browser only: the
 *   media element to drive. A native implementation ignores the argument and
 *   returns; its engine is bound by the shell.
 * @property {function(): void} detach Lets go of the engine and its listeners.
 * @property {function(): boolean} ready True once commands will be acted on.
 * @property {function({url: string, trackId?: string|null, position?: number,
 *   autoplay?: boolean}): Promise<void>} load Points the engine at something to
 *   play. `position` is seconds to start at, `autoplay` awaits playback and
 *   rejects if it was refused.
 * @property {function(): Promise<void>} play
 * @property {function(): void} pause
 * @property {function(): void} stop Stops and lets go of the source; `status`
 *   becomes `idle`.
 * @property {function(number): void} seek Seconds from the start.
 * @property {function(number): void} setVolume 0..1.
 * @property {function(number): void} setRate 1 is normal speed.
 * @property {function({enabled: boolean, gains: number[], preamp: number}): boolean} setEqualizer
 *   Ten bands in dB plus a preamp in dB; returns whether the curve is in effect.
 *   The browser builds a Web Audio graph, Android maps this onto its own
 *   equalizer.
 * @property {function({title?: string, artist?: string, album?: string,
 *   artworkUrl?: string, duration?: number}|null): void} setNowPlaying What the
 *   OS shows -- notification, lock screen, car head unit. `duration` is the
 *   length the library reported, used when the engine measured none.
 * @property {function({play?: Function, pause?: Function, next?: Function,
 *   previous?: Function, seekTo?: function(number): void}): void} setCommandHandlers
 *   What a transport control outside the app does. The queue lives in the UI, so
 *   `next` and `previous` come back to it.
 * @property {function(PlayerEvent, function(PlayerState): void): function(): void} on
 * @property {function(): PlayerState} state
 * @property {function(): HTMLMediaElement|null} element Browser only, for the
 *   few modules that still speak to the element directly; null elsewhere.
 */

/**
 * @typedef {object} PlatformStorage Music kept on the device.
 * @property {boolean} supported False in a browser tab; the Downloads screen
 *   hides itself on it.
 * @property {function({method: string, params?: object}): Promise<object>} query A
 *   Subsonic-shaped request answered from local files, returning the body a
 *   Subsonic call would have, so a list component never learns a second data
 *   source. A method the device cannot answer returns the empty success body
 *   rather than an error. `src/lib/subsonic.js` is the only caller.
 * @property {function(string|string[], {pin?: boolean}=): Promise<{requested: number,
 *   unknown: number}>} download Track ids. `pin` keeps the files through a cache sweep.
 * @property {function(): Promise<Array<{id: string, title: string, artist: string,
 *   album: string, duration: number, state: string}>>} list What is on the device.
 *   Note there is no per-item byte count: `size()` is the only exact figure, and the
 *   Downloads screen estimates the rest. See `downloads.js`.
 * @property {function(string|string[]): Promise<void>} remove
 * @property {function(string[]): Promise<Record<string,
 *   'none'|'queued'|'running'|'done'|'failed'>>} stateOf Batched per list.
 * @property {function(string): Promise<boolean>} isLocal
 * @property {function(): Promise<number>} size Bytes used.
 * @property {function(): Promise<boolean>} isOffline Whether there is no route to
 *   the server. Advisory: a caller still tries the server and falls back on a
 *   failure, because a reachable internet is not a reachable LAN.
 * @property {function(function({id: string, state: string, progress: number}): void):
 *   function(): void} onProgress `progress` is a percentage, 0 to 100, and 0
 *   whenever the server sent no content length to measure against.
 * @property {function(function({online: boolean}): void): function(): void} onConnectivity
 */

/**
 * @typedef {object} PlatformSpeech Voice input.
 * @property {boolean} supported False in a browser tab.
 * @property {function({locale?: string}=): Promise<void>} start
 * @property {function(): void} stop
 * @property {function(function({text: string}): void): function(): void} onPartial
 * @property {function(function({text: string}): void): function(): void} onFinal
 */

/**
 * @typedef {object} PlatformDiagnostics What the user did, for a crash report.
 * @property {boolean} supported
 * @property {function(string, object=): void} log A short, stable action name.
 * @property {function(): Array<{action: string, at: number, detail: object|null}>} report
 *   Oldest first, at most the last 50.
 * @property {function(): void} clear
 */

/**
 * @typedef {object} PlatformSystem The shell itself.
 * @property {boolean} isNative
 * @property {function(): {subsonic: string, mumaApi: string}} serverUrl Bases to
 *   build URLs on; an empty string means same origin. Synchronous everywhere: a
 *   shell that has to ask across a bridge caches the answer, and its boot path
 *   pulls it once with `loadServerUrl()` before anything fetches.
 * @property {function(function(): boolean): function(): void} onBack The platform's
 *   back gesture, not browser history. The handler must be synchronous and
 *   return `true` when it used the press -- closing a sheet, a drawer or a
 *   panel, or popping a history entry. Anything else lets the shell close the
 *   app, which is what back at the root of an app does. A browser never fires it.
 * @property {function(function(string): void): function(): void} onDeepLink A
 *   route the router understands, e.g. "album:123".
 * @property {function(function(boolean): void): function(): void} carConnected
 */

/**
 * @typedef {object} Platform
 * @property {PlatformPlayer} player
 * @property {PlatformStorage} storage
 * @property {PlatformSpeech} speech
 * @property {PlatformDiagnostics} diagnostics
 * @property {PlatformSystem} system
 */

/** Everything the browser can do, which is playback and nothing else. */
const browser = {
  player: browserPlayer,
  storage: browserStorage,
  speech: browserSpeech,
  diagnostics: browserDiagnostics,
  system: browserSystem,
};

/**
 * The shell implementation, built at most once.
 *
 * Lazily, because a browser tab imports this module too and must not register
 * plugins it has no bridge for; memoised, because two playback engines alive at
 * the same time is the failure this design exists to prevent, and a second call
 * to `selectPlatform` inside the shell must hand back the same engine.
 *
 * @type {Platform|null}
 */
let capacitor = null;

/**
 * Picks the implementation. The single place a shell plugs itself in.
 *
 * It runs once, at import time, on purpose: an app that could change platform
 * halfway would need every caller to re-read `platform`, and the one thing that
 * must never happen is two playback engines being alive at the same time.
 *
 * @param {object} [host] - Where to look for a shell; the global object.
 * @returns {Platform}
 */
export function selectPlatform(host = typeof window === "undefined" ? {} : window) {
  if (host?.Capacitor?.isNativePlatform?.() !== true) return browser;
  capacitor ??= createCapacitorPlatform();
  return capacitor;
}

/** @type {Platform} */
export const platform = selectPlatform();

export default platform;
