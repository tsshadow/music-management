import { platform as defaultPlatform } from "./platform/index.js";

/**
 * The start-up check and the "Wachten op server" loop (docs/designs/app-start-reachability/).
 *
 * The shell asks the server once, before it restores the queue: one Subsonic `ping`, signed by
 * the app's own client, three seconds at most, classified natively together with Android's
 * network state (`ServerReachability.kt`). Four answers come back and only two of them stop the
 * start: `noNetwork` and `unreachable`. `reachable` and `authFailed` both continue the normal
 * start -- a refused password is the login page's business, not "offline".
 *
 * Nothing here touches the DOM: `bootUnreachable.js` draws the choice, this module decides.
 */

/** The four answers of `platform.storage.checkServer()`. */
export const REACHABILITY = Object.freeze({
  REACHABLE: "reachable",
  NO_NETWORK: "noNetwork",
  UNREACHABLE: "unreachable",
  AUTH_FAILED: "authFailed",
});

/** How long one ping may take before the server counts as unreachable. */
export const CHECK_TIMEOUT_MS = 3000;

/**
 * The waits between automatic attempts while waiting for the server: quick at first, when a
 * server that is restarting comes back, then calmer, capped at thirty seconds.
 */
export const RETRY_DELAYS_MS = Object.freeze([2000, 5000, 10000, 20000, 30000]);

const KNOWN_STATES = new Set(Object.values(REACHABILITY));

/**
 * Whether an answer means the start cannot go on online.
 *
 * @param {string} state - One of `REACHABILITY`.
 * @returns {boolean}
 */
export function isUnreachable(state) {
  return state === REACHABILITY.NO_NETWORK || state === REACHABILITY.UNREACHABLE;
}

/**
 * The wait before automatic attempt `attempt` (0-based), capped at the last entry.
 *
 * @param {number} attempt
 * @returns {number} Milliseconds.
 */
export function retryDelayMs(attempt) {
  const index = Math.min(Math.max(Math.floor(attempt) || 0, 0), RETRY_DELAYS_MS.length - 1);
  return RETRY_DELAYS_MS[index];
}

/**
 * Asks the shell once whether the server answers.
 *
 * Fails open: a shell without the check (an older APK serving this bundle), a check that throws or
 * an answer this module does not know all read as `reachable`, so the check itself can never be
 * the thing that keeps an app from starting.
 *
 * @param {object} [platform] - Injected by the tests.
 * @param {{timeoutMs?: number}} [options]
 * @returns {Promise<{state: string, elapsedMs: number, offlineChosen: boolean, skipped: boolean}>}
 */
export async function checkServer(
  platform = defaultPlatform,
  { timeoutMs = CHECK_TIMEOUT_MS } = {},
) {
  const storage = platform?.storage;
  const skipped = {
    state: REACHABILITY.REACHABLE,
    elapsedMs: 0,
    offlineChosen: false,
    skipped: true,
  };
  if (!storage?.supported || typeof storage.checkServer !== "function") return skipped;
  try {
    const answer = await storage.checkServer({ timeoutMs });
    return {
      state: KNOWN_STATES.has(answer?.state) ? answer.state : REACHABILITY.REACHABLE,
      elapsedMs: Number(answer?.elapsedMs) || 0,
      offlineChosen: answer?.offlineChosen === true,
      skipped: false,
    };
  } catch (error) {
    console.warn("The start-up check failed; starting as if the server answered", error);
    return skipped;
  }
}

/**
 * Keeps asking until the server answers: the "Wachten op server" state.
 *
 * Attempts follow `RETRY_DELAYS_MS`, and one runs at once whenever the device reports that a
 * network came up. Never two at a time. Ends with the first answer that is not unreachable
 * (`reachable` or `authFailed`), or with null when cancelled.
 *
 * @param {object} options
 * @param {function(): Promise<{state: string}>} options.check - One attempt.
 * @param {function(function({online: boolean}): void): function(): void} [options.onConnectivity]
 *   Subscribes to network changes; returns the unsubscribe.
 * @param {boolean} [options.anyChange] - Attempt on every network change, not only on "online".
 *   Offline mode needs it: while the listener's choice holds, the device reports "offline"
 *   whatever the network does, so an "online" event never comes.
 * @param {function(object): void} [options.onUpdate] - Told `{checking: true}` when an attempt
 *   starts, and `{state, nextAttemptAt, attempt}` when one ended unreachable.
 * @param {{setTimeout: Function, clearTimeout: Function}} [options.timers] - Injected by the tests.
 * @param {function(): number} [options.now] - Injected by the tests.
 * @returns {{promise: Promise<object|null>, retryNow: function(): Promise<void>, cancel: function(): void}}
 */
export function waitForServer({
  check,
  onConnectivity = () => () => {},
  anyChange = false,
  onUpdate = () => {},
  timers = globalThis,
  now = Date.now,
}) {
  let attempt = 0;
  let timer = null;
  let checking = false;
  let finished = false;
  let unsubscribe = () => {};
  let resolve;
  const promise = new Promise((done) => {
    resolve = done;
  });

  const finish = (result) => {
    if (finished) return;
    finished = true;
    timers.clearTimeout(timer);
    try {
      unsubscribe();
    } catch (error) {
      console.warn("Could not stop following connectivity", error);
    }
    resolve(result);
  };

  const schedule = (state) => {
    const delay = retryDelayMs(attempt);
    attempt += 1;
    onUpdate({ state, attempt, nextAttemptAt: now() + delay, checking: false });
    timer = timers.setTimeout(run, delay);
  };

  async function run() {
    if (finished || checking) return;
    timers.clearTimeout(timer);
    checking = true;
    onUpdate({ checking: true, attempt });
    let result;
    try {
      result = await check();
    } catch (error) {
      console.warn("A server check failed", error);
      result = { state: REACHABILITY.UNREACHABLE };
    } finally {
      checking = false;
    }
    if (finished) return;
    if (!isUnreachable(result?.state)) {
      finish(result);
      return;
    }
    schedule(result.state);
  }

  try {
    unsubscribe =
      onConnectivity(({ online } = {}) => {
        if (online || anyChange) run();
      }) ?? (() => {});
  } catch (error) {
    console.warn("Could not follow connectivity while waiting for the server", error);
  }
  schedule(null);
  return { promise, retryNow: run, cancel: () => finish(null) };
}
