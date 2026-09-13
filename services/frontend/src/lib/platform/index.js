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
 * - Jam sync is the one thing that stays entirely outside this interface: it is UI state, it lives
 *   in the web module, and it drives `player` through the ordinary calls. The queue, shuffle,
 *   repeat, radio and the news are different -- on a shell where `ownsQueue` is true, the service
 *   is the one deciding what plays next, so it has to be told about each of them for the same
 *   reason it has to be told the queue itself; `setQueue`, `setMode`, `startRadio`/`stopRadio` and
 *   `toggleNews` are that hand-off. A browser answers all four with an inert default and keeps
 *   deciding for itself, the way `browser/player.js` documents.
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
 * @property {boolean} [shuffle] Native only. Whether the platform service is shuffling its queue.
 *   Absent on a browser -- `ownsQueue` is what a caller branches on, not this field's presence.
 * @property {'none'|'all'|'one'} [repeat] Native only, alongside `shuffle`.
 * @property {string|null} [radioChannel] Native only. The channel slug the service is following,
 *   or null when it is not doing radio. Set by `startRadio`/`stopRadio`, but also by anything else
 *   that can start or stop it on the far side -- Android Auto's browse tree, Assistant -- which is
 *   why a caller reads this rather than only trusting its own last call.
 * @property {boolean} [newsPlaying] Native only, alongside `radioChannel`. Whether a bulletin is
 *   playing right now; `toggleNews` is the only way to change it from here, but the service can
 *   also end one on its own when the bulletin runs out.
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
 * @property {function({shuffle: boolean, repeat: 'none'|'all'|'one'}): Promise<PlayerState>} setMode
 *   Where shuffle and repeat live when `ownsQueue` is true: on the platform service, which already
 *   applies both to its own queue and stops needing this call answered before it can be trusted --
 *   the returned state is the fresh snapshot, for a caller that mirrors it straight into its own
 *   store rather than waiting for the next event. A browser has nowhere to put either flag but
 *   the store; see `browser/player.js`.
 * @property {function(string): Promise<void>} startRadio Tunes into a channel by slug. Native
 *   only in effect: the service streams it and locks onto the server's timeline itself, reusing
 *   Android Auto's own radio support rather than a second implementation of it. A browser answers
 *   and does nothing -- `Player.svelte` drives radio there directly through `radioController.js`
 *   and the `<audio>` element, and never calls this.
 * @property {function(): Promise<void>} stopRadio Leaves radio mode without starting anything
 *   else. Native only in effect, the mirror of `startRadio`.
 * @property {function(): Promise<void>} toggleNews Plays the latest bulletin, or hands the music
 *   back if one is already running -- one call either way. Native only in effect; see `startRadio`.
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
 * @property {function(): Promise<void>} clearCache Deletes every downloaded file that is not
 *   pinned, after cancelling whatever is queued or downloading. What the device-settings tab's
 *   "Clear cache" row calls; a browser tab has nothing to delete and resolves at once.
 * @property {function(): Promise<boolean>} isOffline Whether there is no route to
 *   the server. Advisory: a caller still tries the server and falls back on a
 *   failure, because a reachable internet is not a reachable LAN.
 * @property {function(function({id: string, state: string, progress: number}): void):
 *   function(): void} onProgress `progress` is a percentage, 0 to 100, and 0
 *   whenever the server sent no content length to measure against.
 * @property {function(function({online: boolean}): void): function(): void} onConnectivity
 */

/**
 * @typedef {object} VoiceExplanation What a resolution says, keyed the way a screen prints it:
 *   `heard` is the words the request arrived as; `understood` is the naming rows joined into one
 *   sentence ("Hardstyle, 2021"), present only when something was resolved; `genre`, `label`,
 *   `artist`, `album`, `playlist`, `year`, `rating`, `sets`, `order` are the same rows individually,
 *   present only when the resolution carries that field; `question` is the term a pending
 *   {@link VoiceQuestion} is about; `reason` is why nothing could be run, present only on
 *   `kind: 'nothing'`. Every value is already the library's own spelling or a fixed token
 *   (`order` is `'released'|'added'|'random'`) -- nothing here needs a further lookup to display.
 * @property {string} [heard]
 * @property {string} [understood]
 * @property {string} [genre]
 * @property {string} [label]
 * @property {string} [artist]
 * @property {string} [album]
 * @property {string} [playlist]
 * @property {string} [year]
 * @property {string} [rating]
 * @property {string} [sets]
 * @property {string} [order]
 * @property {string} [question]
 * @property {string} [reason]
 */

/**
 * @typedef {object} VoiceQuery What plays for a `kind: 'play'` resolution -- run it exactly the way
 *   a preset or a Home card does, through `subsonic.js` and the `playlist`/`currentTrack` stores;
 *   this is data, never a command back to the platform.
 * @property {'filtered'|'item'} type
 * @property {string} [method] `'getSongs'`, for `type: 'filtered'`.
 * @property {Record<string, string>} [params] For `subsonicJson(query.method, params)`; already
 *   in that call's own shape (`clusters` is the JSON string `presetQuery` builds, `sortMethod` is
 *   one of the values `getSongs` accepts).
 * @property {'album'|'playlist'} [kind] For `type: 'item'`: which subsonic call to make.
 * @property {string} [id] For `type: 'item'`.
 * @property {string} [name] For `type: 'item'`, the name as the library spells it.
 */

/**
 * @typedef {object} VoiceQuestion A `kind: 'ask'` resolution's follow-up.
 * @property {string} prompt The term nobody qualified, e.g. `"thunderdome"`.
 * @property {string[]} options The kinds it could be, lower-case: `"genre"|"label"|"artist"|
 *   "album"|"playlist"`. Tapping one re-runs `interpret` with the same text and that kind as
 *   `pinned`; answering by voice re-runs `interpret` with the new words and no `pinned` at all,
 *   the same as any other utterance.
 */

/**
 * @typedef {object} VoiceResolution What `platform.speech.interpret()` answers with.
 * @property {VoiceExplanation} explanation
 * @property {object} resolution
 * @property {'play'|'ask'|'nothing'} resolution.kind
 * @property {VoiceQuery} [resolution.query] Present only for `kind: 'play'`.
 * @property {VoiceQuestion} [resolution.question] Present only for `kind: 'ask'`.
 * @property {Array<{label: string, text: string}>} resolution.trace Every stage the parser and the
 *   resolver went through, oldest first, for the diagnostics panel.
 */

/**
 * @typedef {object} PlatformSpeech Voice input.
 * @property {boolean} supported False in a browser tab; the voice screen and its entry points
 *   hide themselves on it rather than offering a microphone that always rejects.
 * @property {function({locale?: string}=): Promise<void>} start
 * @property {function(): void} stop
 * @property {function(function({text: string}): void): function(): void} onPartial
 * @property {function(function({text: string}): void): function(): void} onFinal
 * @property {function({text: string, hypotheses?: string[], entryPoint?: string, pinned?: string}):
 *   Promise<VoiceResolution>} interpret Runs `text` -- and, failing that, `hypotheses` in order --
 *   through the same parser and resolver Android Auto and the microphone use. Never plays anything
 *   itself: the caller runs `resolution.query` through its own queue on `kind: 'play'`. `pinned` is
 *   one of a standing question's `options`, answering it without re-speaking the whole request.
 * @property {function(): Promise<{title: string, html: string}>} vocabulary What the "what MuMa
 *   understands" page shows, from the same string resources the legacy screen used -- `html` may
 *   contain `<b>` and `\n`, exactly as a string resource does.
 * @property {function(): Promise<{traces: Array<{summary: string, lines: Array<{label: string,
 *   text: string}>}>}>} trace The recent voice requests, newest first, for the diagnostics panel.
 */

/**
 * @typedef {object} PlatformDiagnostics What the user did, for a crash report.
 * @property {boolean} supported
 * @property {function(string, object=): void} log A short, stable action name.
 * @property {function(): Array<{action: string, at: number, detail: object|null}>} report
 *   Oldest first, at most the last 50.
 * @property {function(): void} clear
 * @property {function({bundleVersion?: string|null, userAgent?: string|null}): void} identify
 *   Tells a report which UI built it, what frontend code it is running and what rendered it. A
 *   browser tab has no report to attach this to and ignores the call.
 */

/**
 * @typedef {object} DeviceSettings The "Apparaat" settings tab's whole state, as
 *   `platform.system.getSettings()` answers it. Every field here except
 *   `cacheLocationUri`, `carModeDeviceCount` and `carModeFullScreenGranted` is also a key
 *   `setSetting` accepts; those three are shown, not edited -- the device-settings tab
 *   sends the user to `openLegacySettings()` for them instead. `carModeFullScreenGranted`
 *   is absent entirely rather than `false` where the question does not apply (below
 *   Android 14): a missing key means "not applicable", not "denied".
 * @property {boolean} wifiOnly
 * @property {number} parallelDownloads
 * @property {number} cacheSizeMB `-1` means no limit.
 * @property {string} cacheLocationUri Read-only; empty means the default location.
 * @property {number} maxBitrateMobile Kbps; `0` means no limit.
 * @property {number} maxBitrateWifi Kbps; `0` means no limit.
 * @property {number} preloadCount `-1` means the whole queue.
 * @property {boolean} resumeOnHeadphonesPlug
 * @property {number} resumeOnBluetoothDevice `0` any device, `1` A2DP only, `2` never.
 * @property {number} pauseOnBluetoothDevice Same three values as `resumeOnBluetoothDevice`.
 * @property {boolean} hardwareOffload
 * @property {boolean} carModeManual
 * @property {number} carModeDeviceCount Read-only: how many Bluetooth devices are marked
 *   as "this is my car".
 * @property {boolean} [carModeFullScreenGranted] Read-only; absent where not applicable.
 * @property {boolean} scrobbleEnabled
 */

/**
 * @typedef {object} PlatformSystem The shell itself.
 * @property {boolean} isNative
 * @property {function(): {subsonic: string, mumaApi: string}} serverUrl Bases to
 *   build URLs on; an empty string means same origin. Synchronous everywhere: a
 *   shell that has to ask across a bridge caches the answer, and its boot path
 *   pulls it once with `loadServerUrl()` before anything fetches.
 * @property {function(): Promise<void>} signOut Ends the session on the phone -- the
 *   stored password, the muma API key/user id and the muma tokens, plus whatever the
 *   platform service had queued. A browser tab has none of that and resolves at once.
 *   Downloaded files are never touched by this. The caller still owns clearing its own
 *   stores and reloading; this only has to make sure the next boot has nothing left to
 *   sign back in with.
 * @property {function({url?: string, username: string, password: string}): Promise<void>}
 *   saveCredentials Writes a pair the web login screen just verified back to the phone,
 *   so downloads, Android Auto and the legacy UI see the same session afterwards. A
 *   browser tab has nowhere to put it and resolves at once.
 * @property {function(function(): boolean): function(): void} onBack The platform's
 *   back gesture, not browser history. The handler must be synchronous and
 *   return `true` when it used the press -- closing a sheet, a drawer or a
 *   panel, or popping a history entry. Anything else lets the shell close the
 *   app, which is what back at the root of an app does. A browser never fires it.
 * @property {function(function(string): void): function(): void} onDeepLink A
 *   route the router understands, e.g. "album:123".
 * @property {function(function(boolean): void): function(): void} carConnected
 * @property {function(): Promise<DeviceSettings>} getSettings The "Apparaat" settings tab's
 *   whole state in one call. A browser tab answers `{}`; the tab is hidden there anyway
 *   (`system.isNative` is how it decides), so an empty object is never read.
 * @property {function({key: string, value: boolean|number}): Promise<void>} setSetting
 *   Writes one field of {@link DeviceSettings}. Rejects on a key the native whitelist does
 *   not recognise or a value of the wrong type; a browser tab resolves without writing
 *   anything, for the same reason `getSettings` answers empty there.
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
