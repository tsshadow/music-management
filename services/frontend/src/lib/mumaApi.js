/**
 * One definition of how to reach the MuMa API.
 *
 * `Management.svelte` used to own both of these as component-local values and pass
 * them to every tab as props. The curation edit pages live outside Management and
 * cannot receive those props, and a second copy of "which header carries the key"
 * is exactly the kind of thing that drifts. So both moved here; Management still
 * passes them down, so its tabs did not have to change.
 */
import { get } from "svelte/store";

import { mumaApiKey, mumaApiUrl } from "./store";
import { MAX_PARALLEL_MUMA_CALLS, gatedFetch } from "./mumaGate.js";

// `restUrl` builds on `credentials`, which lives in `store.js`; re-exported
// here so a module that already reaches for `apiBase`/`getHeaders` does not
// need a second import just to reach the Subsonic side of the same contract.
export { restUrl } from "./store";

/** Base URL of the MuMa API, as configured for this deployment. `apiBase()` and
 * `mumaApiUrl` are the one resolver for every `/api/*` call -- nothing else
 * should decide this base for itself. */
export function apiBase() {
  return get(mumaApiUrl);
}

/**
 * Request headers carrying the API key, when there is one.
 *
 * The key is left out entirely rather than sent empty: an absent header reads as
 * "unauthenticated" to the backend, while `X-API-Key: ''` reads as a bad key and
 * counts against the login rate limiter.
 *
 * @param {Object} [extra] - Additional headers, e.g. a content type.
 * @returns {Object}
 */
export function getHeaders(extra = {}) {
  const headers = { ...extra };
  const key = get(mumaApiKey);
  if (key) headers["X-API-Key"] = key;
  return headers;
}

/** Headers for a request with a JSON body. */
export function jsonHeaders() {
  return getHeaders({ "Content-Type": "application/json" });
}

// The cap on calls in flight lives in `mumaGate.js`, below every caller, so
// that `store.js` (which this module imports) can go through it too.
export {
  GATE_RETRY_DELAYS_MS,
  MAX_PARALLEL_MUMA_CALLS,
  gatedFetch,
  withMumaGate,
} from "./mumaGate.js";

/**
 * `items.map(worker)`, but with at most `limit` running at once.
 *
 * Results come back in the order of `items`, like `Promise.all`, so callers can
 * destructure a batch of requests exactly as they did before. The gate already
 * caps everything that goes through `fetchMumaJson`; this keeps a screen from
 * queueing its whole batch at once ahead of whatever else the user does next.
 *
 * @template T, R
 * @param {T[]} items
 * @param {(item: T, index: number) => Promise<R>} worker
 * @param {number} [limit]
 * @returns {Promise<R[]>}
 */
export async function mapWithLimit(items, worker, limit = MAX_PARALLEL_MUMA_CALLS) {
  const results = new Array(items.length);
  let next = 0;

  async function runner() {
    for (let index = next++; index < items.length; index = next++) {
      results[index] = await worker(items[index], index);
    }
  }

  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, runner));
  return results;
}

/**
 * A MuMa answer that was not a success. Carries the status and, when the server sent JSON, the
 * parsed body -- `/health` answers 503 with a full report, and a caller may still want to read it
 * -- so that no caller has to mistake an error body for data again.
 */
export class MumaHttpError extends Error {
  /**
   * @param {number} status
   * @param {any} body - The parsed JSON body, or null when there was none.
   * @param {Object} [options] - Passed to `Error`, e.g. `{ cause }`.
   */
  constructor(status, body, options) {
    super(`MuMa answered with status ${status}`, options);
    this.name = "MumaHttpError";
    this.status = status;
    this.body = body;
  }
}

/**
 * GET a MuMa endpoint and parse its answer.
 *
 * Retries a 503 -- what the LMS proxy returns when its concurrency gate is full
 * -- and otherwise turns a body that is not JSON into an error naming the
 * status. Left to itself, `Response.json()` reports the refusal as
 * `Unexpected token 'T', "Too many r"... is not valid JSON`, which reads like a
 * malformed API and sends every reader to the wrong side of the connection.
 *
 * A non-2xx answer throws a {@link MumaHttpError} even when its body is JSON: a
 * `{"detail": "Forbidden"}` returned as data is how a 401 used to become an empty
 * list, cached for the rest of the session.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<any>} The parsed body.
 * @throws {MumaHttpError} On a non-2xx status.
 */
export async function fetchMumaJson(url, options = {}) {
  const response = await gatedFetch(url, options);
  let body;
  try {
    body = await response.json();
  } catch (err) {
    if (!response.ok) throw new MumaHttpError(response.status, null, { cause: err });
    throw new Error(`MuMa antwoordde met status ${response.status} en geen JSON`, { cause: err });
  }
  if (!response.ok) throw new MumaHttpError(response.status, body);
  return body;
}
