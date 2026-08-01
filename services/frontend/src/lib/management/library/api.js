/**
 * Fetch helpers for the library browser.
 *
 * Every call checks res.ok. The previous Advanced Library only caught thrown
 * exceptions, so an HTTP 500 left the track list at [] and rendered "No tracks
 * found" -- which is how a completely broken endpoint stayed invisible.
 */

export function emptyFilters() {
  return {
    q: '',
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

const LIST_KEYS = ['genre', 'artist', 'label'];
const SCALAR_KEYS = ['q', 'bpm_min', 'bpm_max', 'year_min', 'year_max', 'analyzed'];

export function buildQuery(filters) {
  const params = new URLSearchParams();
  for (const key of SCALAR_KEYS) {
    const value = filters[key];
    if (value === null || value === undefined || value === '') continue;
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
  const url = `${API_BASE}${path}${query ? `?${query}` : ''}`;

  let res;
  try {
    res = await fetch(url, { headers: getHeaders() });
  } catch (err) {
    throw new Error(`Server niet bereikbaar (${path}).`);
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Serverfout ${res.status} bij ${path}. ${detail.slice(0, 200)}`.trim());
  }
  return res.json();
}
