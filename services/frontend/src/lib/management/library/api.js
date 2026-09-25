/**
 * Fetch helpers for the library browser.
 *
 * Every call checks res.ok. The previous Advanced Library only caught thrown
 * exceptions, so an HTTP 500 left the track list at [] and rendered "No tracks
 * found" -- which is how a completely broken endpoint stayed invisible.
 */

import { GATE_RETRY_DELAYS_MS } from "../../mumaApi.js";
import { get } from "svelte/store";
import { t } from "../../i18n/index.js";

export function emptyFilters() {
  return {
    q: "",
    genre: [],
    artist: [],
    label: [],
    bpm_min: null,
    bpm_max: null,
    year_min: null,
    year_max: null,
    analyzed: null,
  };
}

const LIST_KEYS = ["genre", "artist", "label"];
const SCALAR_KEYS = ["q", "bpm_min", "bpm_max", "year_min", "year_max", "analyzed"];

export function buildQuery(filters) {
  const params = new URLSearchParams();
  for (const key of SCALAR_KEYS) {
    const value = filters[key];
    if (value === null || value === undefined || value === "") continue;
    params.append(key, String(value));
  }
  for (const key of LIST_KEYS) {
    for (const value of filters[key] || []) {
      if (value) params.append(key, value);
    }
  }
  return params.toString();
}

export async function apiGet(API_BASE, path, filters, getHeaders, extra = {}) {
  const params = new URLSearchParams(buildQuery(filters || {}));
  for (const [key, value] of Object.entries(extra)) {
    if (value !== null && value !== undefined) params.append(key, String(value));
  }
  const query = params.toString();
  const url = `${API_BASE}${path}${query ? `?${query}` : ""}`;

  for (let attempt = 0; ; attempt++) {
    let res;
    try {
      res = await fetch(url, { headers: getHeaders() });
    } catch (err) {
      throw new Error(get(t)("management.library.serverUnreachablePath", { path }), { cause: err });
    }
    // 503 is the LMS proxy saying its concurrency gate is full -- a condition
    // measured in milliseconds, shared with every other MuMa caller. See
    // GATE_RETRY_DELAYS_MS in lib/mumaApi.js.
    if (res.status === 503 && attempt < GATE_RETRY_DELAYS_MS.length) {
      await new Promise((resolve) => setTimeout(resolve, GATE_RETRY_DELAYS_MS[attempt]));
      continue;
    }
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      const message = get(t)("management.library.serverError", {
        status: res.status,
        path,
        detail: detail.slice(0, 200),
      });
      throw new Error(message.trim());
    }
    return res.json();
  }
}
