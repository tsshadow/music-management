/**
 * Utilities for resolving API endpoints across the combined MuMa services.
 */
const API_ROOT = (import.meta.env.VITE_API_BASE ?? '/api').replace(/\/$/, '');

function join(base: string, path: string): string {
  const normalisedBase = base.replace(/\/$/, '');
  if (!path) {
    return normalisedBase;
  }
  const normalisedPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalisedBase}${normalisedPath}`;
}

export const importerApi = {
  base: join(API_ROOT, '/importer'),
  url: (path: string) => join(join(API_ROOT, '/importer'), path),
};

export const scrobblerApi = {
  base: join(API_ROOT, '/scrobbler/v1'),
  url: (path: string) => join(join(API_ROOT, '/scrobbler/v1'), path),
};

/**
 * Convert an HTTP(S) API endpoint into a WebSocket endpoint that matches the
 * current execution environment.
 */
export function websocketUrl(apiEndpoint: string): string {
  if (/^https?:/i.test(apiEndpoint)) {
    return apiEndpoint.replace(/^http/i, 'ws');
  }
  if (typeof window === 'undefined') {
    return apiEndpoint.replace(/^http/i, 'ws');
  }
  const origin = window.location.origin.replace(/^http/i, 'ws');
  const path = apiEndpoint.startsWith('/') ? apiEndpoint : `/${apiEndpoint}`;
  return `${origin}${path}`;
}
