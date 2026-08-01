import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import UsersTab from '../../src/lib/management/tabs/UsersTab.svelte';
import { credentials, mumaUser, userPermissions } from '../../src/lib/store.js';

const USER = { id: 7, username: 'lisa', display_name: 'Lisa', enabled: true, role_name: 'user' };

/**
 * Routes the handful of calls UsersTab fires when a user is selected, so the
 * assertions can focus on the Subsonic-token widget.
 */
function mockApi({ token = '' } = {}) {
  return vi.fn(async (url, options = {}) => {
    if (String(url).includes('/api/admin/subsonic-token')) {
      if (options.method === 'PUT') {
        const sent = JSON.parse(options.body);
        return { ok: true, json: async () => ({ username: 'lisa', token: sent.token }), text: async () => '' };
      }
      return { ok: true, json: async () => ({ username: 'lisa', token }), text: async () => '' };
    }
    return { ok: true, json: async () => ({}), text: async () => '' };
  });
}

function props(overrides = {}) {
  return {
    users: [USER],
    roles: [{ id: 1, name: 'user' }],
    selectedUser: USER,
    API_BASE: '/muma',
    getHeaders: (extra = {}) => ({ ...extra, 'X-API-Key': 'k' }),
    fetchUsers: () => {},
    onMessage: () => {},
    onError: () => {},
    onSelectUser: () => {},
    navigateToScrobbleImport: () => {},
    ...overrides
  };
}

describe('UsersTab -- Subsonic API token', () => {
  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    mumaUser.set({ id: 1, is_admin: true });
    userPermissions.set([]);
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows that the selected user has no token yet', async () => {
    render(UsersTab, props());

    await waitFor(() => expect(screen.getByText('Geen token ingesteld')).toBeTruthy());
    expect(screen.getByText('TOKEN GENEREREN')).toBeTruthy();
  });

  it('shows an existing token and offers to revoke it', async () => {
    globalThis.fetch = mockApi({ token: 'abc123' });

    render(UsersTab, props());

    await waitFor(() => expect(screen.getByText('abc123')).toBeTruthy());
    expect(screen.getByText('INTREKKEN')).toBeTruthy();
  });

  it('generates a token for the selected user, authenticated as admin', async () => {
    render(UsersTab, props());
    await waitFor(() => expect(screen.getByText('TOKEN GENEREREN')).toBeTruthy());

    await fireEvent.click(screen.getByText('TOKEN GENEREREN'));

    await waitFor(() => {
      const put = globalThis.fetch.mock.calls.find((c) => c[1]?.method === 'PUT');
      expect(put).toBeTruthy();
      expect(put[0]).toContain('/api/admin/subsonic-token');
      expect(put[0]).toContain('username=lisa');
      expect(put[0]).toContain('u=user');
      expect(JSON.parse(put[1].body).token).toMatch(/^[0-9a-f]{32}$/);
    });
  });

  it('revoking sends an empty token', async () => {
    globalThis.fetch = mockApi({ token: 'abc123' });

    render(UsersTab, props());
    await waitFor(() => expect(screen.getByText('INTREKKEN')).toBeTruthy());

    await fireEvent.click(screen.getByText('INTREKKEN'));

    await waitFor(() => {
      const put = globalThis.fetch.mock.calls.find((c) => c[1]?.method === 'PUT');
      expect(put).toBeTruthy();
      expect(JSON.parse(put[1].body).token).toBe('');
    });
    await waitFor(() => expect(screen.getByText('Geen token ingesteld')).toBeTruthy());
  });

  it('asks for server credentials instead of showing a dead widget', async () => {
    credentials.set({ url: '', username: '', password: '' });

    render(UsersTab, props());

    await waitFor(() =>
      expect(screen.getByText('Vereist een login met server-inloggegevens op de playerpagina.')).toBeTruthy()
    );
    expect(globalThis.fetch.mock.calls.some((c) => String(c[0]).includes('subsonic-token'))).toBe(false);
  });
});
