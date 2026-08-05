import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Management from '../../src/lib/management/Management.svelte';
import {
  activeManagementTab, credentials, mumaApiKey, mumaUser, userPermissions
} from '../../src/lib/store.js';

const STATS = {
  total_tracks: 12345, total_artists: 678, total_scrobbles: 90123, match_rate: 92,
  avg_track_duration: 245, total_unmatched: 42, top_genres: [], recently_added: []
};

const USER = { id: 1, username: 'user', display_name: 'Teun', permissions: ['users.read'] };

/** Answers every endpoint Management loads on arrival. */
function api({ configOk = true, verify = { type: 'user', user: USER }, loginOk = true } = {}) {
  const bodies = {
    '/api/config': { version: '0.0.57' },
    '/api/notes': { release_notes: '<p>Notes</p>' },
    '/api/rules': { genres: [] },
    '/api/soundcloud': [],
    '/api/youtube': [],
    '/api/versions': [],
    '/api/all-notes': {},
    '/api/scrobble/import/latest': [],
    '/api/users': [USER],
    '/api/system/containers': [{ name: 'music-manager', image: 'muma:0.0.57', status: 'running' }],
    '/api/system/activity': { recent_added: [], recent_tagged: [] },
    '/api/stats': STATS,
    '/api/roles': [],
    '/api/artist-images/stats': { total: 0, missing: 0 }
  };

  return vi.fn(async (url, options = {}) => {
    if (url.includes('/api/auth/login')) {
      return { ok: loginOk, json: async () => ({ api_key: 'key-from-login' }) };
    }
    if (url.includes('/api/auth/verify')) {
      return { ok: true, json: async () => verify };
    }
    if (url.includes('/api/config') && !configOk) {
      return { ok: false, json: async () => ({}) };
    }
    const match = Object.keys(bodies).find((path) => url.includes(path));
    return { ok: true, json: async () => (match ? bodies[match] : {}) };
  });
}

describe('Management', () => {
  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    mumaApiKey.set('key-1');
    // The screen is gated on being an administrator; without this it renders the
    // access-denied panel instead of any tab. The verify call overwrites both.
    mumaUser.set({ id: 1, username: 'user', is_admin: true });
    userPermissions.set(['users.read']);
    activeManagementTab.set('overview');
    globalThis.fetch = api();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens on the overview once everything is loaded', async () => {
    render(Management);

    await waitFor(() => expect(screen.getByText('1 / 1 Running')).toBeTruthy());
  });

  it('loads its data with the stored api key', async () => {
    render(Management);

    await waitFor(() => expect(screen.getByText('1 / 1 Running')).toBeTruthy());
    const [, options] = globalThis.fetch.mock.calls.find(([url]) => url.includes('/api/config'));
    expect(options.headers['X-API-Key']).toBe('key-1');
  });

  it('logs in with the player credentials when there is no key yet', async () => {
    mumaApiKey.set('');

    render(Management);

    await waitFor(() => expect(get(mumaApiKey)).toBe('key-from-login'));
  });

  it('a failed auto-login leaves the management screen closed', async () => {
    mumaApiKey.set('');
    globalThis.fetch = api({ loginOk: false });

    render(Management);

    await waitFor(() => expect(screen.queryByText('1 / 1 Running')).toBeNull());
  });

  it('a key the server rejects leaves the management screen closed', async () => {
    globalThis.fetch = api({ configOk: false });

    render(Management);

    await waitFor(() => expect(screen.queryByText('1 / 1 Running')).toBeNull());
  });

  it('the signed-in user and their permissions are published', async () => {
    render(Management);

    await waitFor(() => expect(get(mumaUser)).toEqual(USER));
    expect(get(userPermissions)).toEqual(['users.read']);
  });

  it('the shared system key counts as an administrator', async () => {
    globalThis.fetch = api({ verify: { type: 'system' } });

    render(Management);

    await waitFor(() => expect(get(userPermissions)).toEqual([]));
    expect(get(mumaUser)?.is_admin).toBe(true);
  });

  it('the health tab is reachable', async () => {
    activeManagementTab.set('health');

    render(Management);

    await waitFor(() => expect(screen.getByText('Docker Containers')).toBeTruthy());
  });

  it('the notifications tab is reachable', async () => {
    activeManagementTab.set('notifications');

    render(Management);

    await waitFor(() => expect(screen.getByText('Meldingen')).toBeTruthy());
  });

  it('the user requests tab is reachable', async () => {
    activeManagementTab.set('user-requests');

    render(Management);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('/api/user-requests'))).toBe(true)
    );
  });

  it('the genre curation tab is reachable', async () => {
    activeManagementTab.set('genre-curation');

    render(Management);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('/api/rules/genres'))).toBe(true)
    );
  });

  it('survives a server it cannot reach at all', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(Management);

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
  });
});
