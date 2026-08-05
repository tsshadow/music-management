import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import TopBar from '../../src/lib/TopBar.svelte';
import { activeModal, activeView, credentials } from '../../src/lib/store.js';

function subsonic({ serverVersion = '0.0.57', releases = [{ version: '0.0.57', notes: 'Nieuw' }] } = {}) {
  return vi.fn(async (url) => {
    if (url.includes('/release-notes.json')) return { ok: true, json: async () => releases };
    if (url.includes('/rest/getGenres')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { genres: { genre: [] } } }) };
    }
    return { ok: true, json: async () => ({ 'subsonic-response': { status: 'ok', serverVersion } }) };
  });
}

describe('TopBar', () => {
  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    activeView.set('home');
    activeModal.set(null);
    window.localStorage.clear();
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the greeting on the home screen', () => {
    render(TopBar, { greeting: 'Goedemiddag' });

    expect(screen.getByText('Goedemiddag')).toBeTruthy();
  });

  it('the greeting stays away on other screens', () => {
    activeView.set('albums');

    render(TopBar, { greeting: 'Goedemiddag' });

    expect(screen.queryByText('Goedemiddag')).toBeNull();
  });

  it('remembers the server version on a first visit', async () => {
    render(TopBar, { greeting: '' });

    await waitFor(() => expect(window.localStorage.getItem('lms_last_version')).toBe('0.0.57'));
    expect(get(activeModal)).toBeNull();
  });

  it('shows the release notes after the server was upgraded', async () => {
    window.localStorage.setItem('lms_last_version', '0.0.56');

    render(TopBar, { greeting: '' });

    await waitFor(() => expect(get(activeModal)?.type).toBe('release-notes'));
    expect(get(activeModal).data.releases).toHaveLength(1);
  });

  it('an unchanged version shows nothing', async () => {
    window.localStorage.setItem('lms_last_version', '0.0.57');

    render(TopBar, { greeting: '' });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(get(activeModal)).toBeNull();
  });

  it('only releases newer than the last seen one are shown', async () => {
    window.localStorage.setItem('lms_last_version', '0.0.56');
    globalThis.fetch = subsonic({
      releases: [{ version: '0.0.55', notes: 'Oud' }, { version: '0.0.57', notes: 'Nieuw' }]
    });

    render(TopBar, { greeting: '' });

    await waitFor(() => expect(get(activeModal)?.type).toBe('release-notes'));
    expect(get(activeModal).data.releases.map((r) => r.version)).toEqual(['0.0.57']);
  });

  it('a downgrade shows nothing', async () => {
    window.localStorage.setItem('lms_last_version', '0.0.58');

    render(TopBar, { greeting: '' });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(get(activeModal)).toBeNull();
  });

  it('survives a version check that never arrives', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(TopBar, { greeting: 'Goedemiddag' });

    await waitFor(() => expect(screen.getByText('Goedemiddag')).toBeTruthy());
  });
});
