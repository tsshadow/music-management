/**
 * One queue for every call this client makes to MuMa.
 *
 * Every `/api/...` call reaches MuMa through the LMS proxy
 * (services/music-management-server/src/libs/muma/MumaResource.cpp), which holds one
 * http server thread for the whole round trip and refuses anything past half the pool
 * rather than queueing it. The pool defaults to the logical CPU count, so on production
 * (8 cores) that gate is four calls -- and it is shared with whatever the player is doing
 * at the same time, artist images most of all.
 *
 * A refusal is a 503 carrying the bare line "Too many requests to MuMa in flight", which
 * is not JSON: parsing it throws, and a screen that loads its panels in one batch loses
 * every panel to the one that was refused.
 *
 * Capping each batch on its own was not enough: opening the home screen fires a dozen
 * calls from as many modules (session check, account settings, presets, genre tints, the
 * feed list, the release radar, three daily mixes, artist images), each keeping to its
 * own limit and all of them together blowing through the gate. So the cap lives here,
 * below every caller, and counts across all of them.
 *
 * This module imports nothing so `store.js` and `mumaApi.js` can both reach it.
 */

/** How many MuMa calls this client keeps in flight at once, all modules together. Three
 * of production's four, so the player's own image traffic still has a slot. */
export const MAX_PARALLEL_MUMA_CALLS = 3;

/**
 * How long to wait before asking again after the proxy refused a call.
 *
 * A refusal means the gate was full at that instant, not that anything is wrong: the
 * calls holding it are round trips that finish in milliseconds. Staying under the cap
 * lowers the odds of a refusal without ruling one out (another tab, the player, the
 * mobile app on the same account), so a refusal is waited out rather than reported --
 * for several seconds in total, because from the user's side there is no difference
 * between one call and a hundred and the proxy in between is not their problem. Each
 * delay is jittered by up to its own length so a batch refused together does not retry
 * together and collide again.
 */
export const GATE_RETRY_DELAYS_MS = [100, 300, 700, 1500, 3000];

let inFlight = 0;
/** @type {Array<() => void>} */
const waiting = [];

/** How many calls hold a slot right now. Tests read this; nothing in the app does. */
export function mumaCallsInFlight() {
  return inFlight;
}

/**
 * Runs `work` once a slot is free, and frees it afterwards.
 *
 * A finishing call hands its slot straight to the next waiter instead of releasing and
 * letting the waiter re-acquire, so a newcomer cannot slip in between and push the count
 * past the cap.
 *
 * @template R
 * @param {() => Promise<R>} work
 * @returns {Promise<R>}
 */
export async function withMumaGate(work) {
  if (inFlight >= MAX_PARALLEL_MUMA_CALLS) {
    await new Promise((resolve) => waiting.push(resolve));
  } else {
    inFlight += 1;
  }
  try {
    return await work();
  } finally {
    const next = waiting.shift();
    if (next) next();
    else inFlight -= 1;
  }
}

function jittered(ms) {
  return ms + Math.floor(Math.random() * ms);
}

/**
 * How long a refusal asked us to wait, when it said: the LMS proxy sends
 * `Retry-After` in seconds on its own gate refusals. Anything unparseable, or a
 * 503 from further upstream that carries no header, falls back to the ladder.
 *
 * @param {Response} response
 * @param {number} attempt
 * @returns {number} milliseconds
 */
function retryDelay(response, attempt) {
  const header = Number(response?.headers?.get?.("Retry-After"));
  if (Number.isFinite(header) && header > 0) return jittered(header * 1000);
  return jittered(GATE_RETRY_DELAYS_MS[attempt]);
}

/**
 * `fetch`, but through the gate, and retrying a 503 -- what the proxy returns when its
 * gate is full anyway. The slot is released between attempts so the calls ahead of this
 * one can finish and make room.
 *
 * Returns the `Response` untouched so callers keep reading status and body as they did.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<Response>}
 */
export async function gatedFetch(url, options = {}) {
  for (let attempt = 0; ; attempt++) {
    const response = await withMumaGate(() => fetch(url, options));
    if (response?.status !== 503 || attempt >= GATE_RETRY_DELAYS_MS.length) return response;
    await new Promise((resolve) => setTimeout(resolve, retryDelay(response, attempt)));
  }
}

/** Resets the queue. Tests use this between cases; nothing in the app does. */
export function resetMumaGate() {
  inFlight = 0;
  waiting.length = 0;
}
