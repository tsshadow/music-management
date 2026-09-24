/**
 * Two queues for the calls this client makes to MuMa, one per hop.
 *
 * Until MR !833 every `/api/...` call reached MuMa through the LMS proxy
 * (services/music-management-server/src/libs/muma/MumaResource.cpp), which holds one
 * http server thread for the whole round trip and refuses anything past half the pool
 * rather than queueing it -- a 503 carrying the bare line "Too many requests to MuMa in
 * flight", which is not JSON, so a screen that loaded its panels in one batch lost every
 * panel to the one that was refused. Capping each batch on its own was not enough:
 * opening the home screen fires a dozen calls from as many modules, each keeping to its
 * own limit and all of them together blowing through the gate. So the cap lives here,
 * below every caller, and counts across all of them.
 *
 * Since !833 nginx sends most of `/muma/api/` straight to the Python server; only the
 * routes LMS implements itself (admin, the artist image, the native artist id,
 * `tracks/<id>/refresh`, `/muma/users/`) still pass the proxy and its gate. The login
 * left that list when LMS stopped answering it with its own shared key: it goes to MuMa
 * directly, like everything else. A single queue
 * sized for that gate then held the direct calls hostage: with four feed builds of
 * seconds each in it, the session check, the settings read and the presets waited behind
 * a feed. So the queue is two lanes (docs/designs/feeds/home-load.md, step 1):
 *
 * - `proxy`: the LMS-owned routes, three of production's four proxy slots, so the
 *   player's own image traffic still has one;
 * - `direct`: everything else, eight at once -- bounded so a burst of feed misses cannot
 *   exhaust the Python server's connection pool, wide enough that nothing cheap queues
 *   behind something slow.
 *
 * `gatedFetch` picks the lane from the URL; `withMumaGate` defaults to the proxy lane so
 * a caller that does not say keeps the safe behaviour. This module imports nothing so
 * `store.js` and `mumaApi.js` can both reach it.
 */
export const MAX_PARALLEL_LMS_PROXY_CALLS = 3;
/** The name `mapWithLimit` and older callers know the proxy cap by. */
export const MAX_PARALLEL_MUMA_CALLS = MAX_PARALLEL_LMS_PROXY_CALLS;
export const MAX_PARALLEL_DIRECT_CALLS = 8;

/**
 * The routes LMS still owns: the regex location in
 * services/music-management-server/nginx/reverse-proxy.conf, minus its `/muma` prefix. A
 * route added to that location belongs here too, or its calls run in the wrong lane.
 */
const LMS_ROUTES =
  /^\/(api\/admin\/|api\/artists\/[^/]+\/image$|api\/artists\/(?:[^/-]*-)?[0-9]+$|api\/tracks\/.+\/refresh$|users\/)/;

/** Extracts the API path independently of the configured deployment base prefix. */
function laneFor(url) {
  const pathname = new URL(url, "http://localhost").pathname;
  const path = pathname.match(/\/(?:api|users)\/.*$/)?.[0] ?? pathname;
  return LMS_ROUTES.test(path) ? "proxy" : "direct";
}

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

const lanes = {
  proxy: { inFlight: 0, waiting: [], limit: MAX_PARALLEL_LMS_PROXY_CALLS },
  direct: { inFlight: 0, waiting: [], limit: MAX_PARALLEL_DIRECT_CALLS },
};

/** Total calls holding a slot across both lanes, for tests. */
export function mumaCallsInFlight() {
  return lanes.proxy.inFlight + lanes.direct.inFlight;
}

/**
 * Runs work in its lane, handing a released slot directly to the next waiter.
 * @template R
 * @param {() => Promise<R>} work
 * @param {"proxy" | "direct"} [lane="proxy"]
 * @returns {Promise<R>}
 */
export async function withMumaGate(work, lane = "proxy") {
  const state = lanes[lane];
  if (state.inFlight >= state.limit) {
    await new Promise((resolve) => state.waiting.push(resolve));
  } else {
    state.inFlight += 1;
  }
  try {
    return await work();
  } finally {
    const next = state.waiting.shift();
    if (next) next();
    else state.inFlight -= 1;
  }
}

/** Adds jitter so concurrent refusals do not retry together. */
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
    const response = await withMumaGate(() => fetch(url, options), laneFor(url));
    if (response?.status !== 503 || attempt >= GATE_RETRY_DELAYS_MS.length) return response;
    await new Promise((resolve) => setTimeout(resolve, retryDelay(response, attempt)));
  }
}

/** Resets the queue. Tests use this between cases; nothing in the app does. */
export function resetMumaGate() {
  for (const state of Object.values(lanes)) {
    state.inFlight = 0;
    state.waiting.length = 0;
  }
}
