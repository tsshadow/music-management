import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Settings from '../../src/lib/Settings.svelte';
import SettingsSidebar from '../../src/lib/SettingsSidebar.svelte';
import { activeSettingsTab, credentials } from '../../src/lib/store.js';

function mockUser() {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({
      'subsonic-response': {
        status: 'ok',
        user: { username: 'user', adminRole: true, uiArtistReleaseSortMethod: 8 }
      }
    })
  }));
}

describe('player settings navigation', () => {
  beforeEach(() => {
    globalThis.fetch = mockUser();
    credentials.set({ url: '', username: 'user', password: 'pw' });
    activeSettingsTab.set('general');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('only offers the personal tabs -- server administration lives in the management view', () => {
    render(SettingsSidebar, { onnavigate: () => {} });

    expect(screen.getByText('Algemeen')).toBeTruthy();
    expect(screen.getByText('Geavanceerd')).toBeTruthy();
    expect(screen.getByText('Over')).toBeTruthy();

    for (const gone of ['Bibliotheken', 'Scan Instellingen', 'Scanner', 'Gebruikers']) {
      expect(screen.queryByText(gone)).toBeNull();
    }
  });

  it('falls back to the general tab when a removed admin tab is still persisted', async () => {
    // An account that last had "scanner" open would otherwise land on a blank screen.
    activeSettingsTab.set('scanner');

    render(Settings);

    await waitFor(() => expect(get(activeSettingsTab)).toBe('general'));
    expect(screen.getByText('Algemene Instellingen')).toBeTruthy();
  });
});
