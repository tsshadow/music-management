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

/** Base URL of the MuMa API, as configured for this deployment. */
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

/**
 * How many MuMa calls this client keeps in flight at once.
 *
 * Every `/api/...` call reaches MuMa through the LMS proxy
 * (services/music-management-server/src/libs/muma/MumaResource.cpp), which holds
 * one http server thread for the whole round trip and refuses anything past half
 * the pool rather than queueing it -- ten calls on production hardware. That
 * allowance is shared with whatever the player is doing at the same time
 * (artist images, most of all), so a screen may not spend all of it.
 *
 * A refusal is a 503 carrying the bare line "Too many requests to MuMa in
 * flight", which is not JSON: parsing it throws, and a screen that loads its
 * panels in one batch loses every panel to the one that was refused.
 */
export const MAX_PARALLEL_MUMA_CALLS = 4;

/**
 * `items.map(worker)`, but with at most `limit` running at once.
 *
 * Results come back in the order of `items`, like `Promise.all`, so callers can
 * destructure a batch of requests exactly as they did before.
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
 * How long to wait before asking again after the proxy refused a call.
 *
 * A refusal means the gate was full at that instant, not that anything is
 * wrong: the calls holding it are round trips that finish in milliseconds, and
 * the allowance is shared with whatever else is talking to MuMa right then.
 * Staying under MAX_PARALLEL_MUMA_CALLS therefore lowers the odds of a refusal
 * without ruling one out, so a refusal is waited out rather than reported.
 */
export const GATE_RETRY_DELAYS_MS = [100, 300, 700];

/**
 * GET a MuMa endpoint and parse its answer.
 *
 * Retries a 503 -- what the LMS proxy returns when its concurrency gate is full
 * -- and otherwise turns a body that is not JSON into an error naming the
 * status. Left to itself, `Response.json()` reports the refusal as
 * `Unexpected token 'T', "Too many r"... is not valid JSON`, which reads like a
 * malformed API and sends every reader to the wrong side of the connection.
 *
 * @param {string} url
 * @param {RequestInit} [options]
 * @returns {Promise<any>} The parsed body.
 */
export async function fetchMumaJson(url, options = {}) {
  for (let attempt = 0; ; attempt++) {
    const response = await fetch(url, options);
    if (response.status === 503 && attempt < GATE_RETRY_DELAYS_MS.length) {
      await new Promise((resolve) => setTimeout(resolve, GATE_RETRY_DELAYS_MS[attempt]));
      continue;
    }
    try {
      return await response.json();
    } catch (err) {
      throw new Error(`MuMa antwoordde met status ${response.status} en geen JSON`, { cause: err });
    }
  }
}
