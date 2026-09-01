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
