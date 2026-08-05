import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Sidebar from '../../src/lib/Sidebar.svelte';
import { credentials, favoriteGenres, viewMode } from '../../src/lib/store.js';

const GENRES = [
  { value: 'Hardcore', songCount: 1200 },
  { value: 'Uptempo', songCount: 400 },
  { value: 'Obscure', songCount: 2 }
];

function subsonic(genres = GENRES) {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({ 'subsonic-response': { genres: { genre: genres } } })
  }));
}

async function renderLoaded(props = {}) {
  const rendered = render(Sidebar, { activeView: 'home', onnavigate: vi.fn(), ...props });
  await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());
  return rendered;
}

describe('Sidebar', () => {
  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    viewMode.set('songs');
    favoriteGenres.set([]);
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists the genres the library has', async () => {
    await renderLoaded();

    expect(screen.getByText('Uptempo')).toBeTruthy();
  });

  it('leaves out genres with almost nothing in them', async () => {
    await renderLoaded();

    expect(screen.queryByText('Obscure')).toBeNull();
  });

  it('shows only the favourites once some are marked', async () => {
    favoriteGenres.set(['Uptempo']);

    render(Sidebar, { activeView: 'home', onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Uptempo')).toBeTruthy());
    expect(screen.queryByText('Hardcore')).toBeNull();
  });

  it('navigating to a genre is reported to the parent', async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getByText('Hardcore'));

    expect(onnavigate).toHaveBeenCalledWith('genre:Hardcore');
  });

  it('navigating to a section is reported to the parent', async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getByText('Albums'));

    expect(onnavigate).toHaveBeenCalledWith('albums');
  });

  it('switching to sets changes the mode', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Sets'));

    expect(get(viewMode)).toBe('sets');
  });

  it('switching back to songs changes the mode', async () => {
    viewMode.set('sets');
    await renderLoaded();

    await fireEvent.click(screen.getByText('Nummers'));

    expect(get(viewMode)).toBe('songs');
  });

  it('survives a genre list that fails to load', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(Sidebar, { activeView: 'home', onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Albums')).toBeTruthy());
  });

  it('copes with a server that returns a single genre rather than a list', async () => {
    globalThis.fetch = subsonic({ value: 'Hardcore', songCount: 1200 });

    await renderLoaded();

    expect(screen.getByText('Hardcore')).toBeTruthy();
  });
});
