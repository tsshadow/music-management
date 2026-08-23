import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import ArtistView from '../../src/lib/ArtistView.svelte';
import {
  credentials, currentTrack, deduplicateEnabled, playerState, playlist, viewMode
} from '../../src/lib/store.js';

const OWN_ALBUM = { id: 'album-1', name: 'Close Combat', artist: 'Angerfist', releaseTypes: ['Album'] };
const OWN_EP = { id: 'album-2', name: 'Raise Your Fist', artist: 'Angerfist', releaseTypes: ['EP'] };
const GUEST_ALBUM = { id: 'album-3', name: 'Various Hardcore', artist: 'Various Artists' };
const TRACK = { id: 'song-1', title: 'Raise Your Fist', artist: 'Angerfist', duration: 240, suffix: 'flac' };

function artist(overrides = {}) {
  return { id: 'artist-1', name: 'Angerfist', album: [OWN_ALBUM], ...overrides };
}

function subsonic({
  artistData = artist(),
  tracks = { track: [TRACK], moreResults: false, nextOffset: 1 },
  info = { biography: 'Hardcore uit Amsterdam.', similarArtist: [{ id: 'artist-2', name: 'Outsiders' }] },
  muma = { genre_rules: [{ genre_id: 12, name: 'Hardcore', created_by: 'user' }] },
  starOk = true
} = {}) {
  return vi.fn(async (url) => {
    if (url.includes('/rest/getArtistInfo2')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { artistInfo2: info } }) };
    }
    if (url.includes('/rest/getSpotifyTracks')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { tracks } }) };
    }
    if (url.includes('/rest/getArtist?')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { artist: artistData } }) };
    }
    // The curation endpoint, keyed by name. The previous version of this mock
    // answered /api/artists/{id} -- a route that has never existed, so the test
    // passed while the chips on the real page stayed empty.
    if (url.includes('/api/curation/artists/')) {
      return { ok: true, json: async () => muma };
    }
    return { ok: starOk, json: async () => ({ 'subsonic-response': { status: 'ok' } }) };
  });
}

async function renderLoaded(props = {}) {
  const rendered = render(ArtistView, { artistId: 'artist-1', onnavigate: vi.fn(), ...props });
  await waitFor(() => expect(screen.getByText('Angerfist')).toBeTruthy());
  return rendered;
}

describe('ArtistView', () => {
  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    viewMode.set('songs');
    deduplicateEnabled.set(false);
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the artist with their biography', async () => {
    await renderLoaded();

    await waitFor(() => expect(screen.getByText(/Hardcore uit Amsterdam/)).toBeTruthy());
  });

  it('shows the genres the management API knows about', async () => {
    await renderLoaded();

    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());
  });

  it('groups the releases by their type', async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: [OWN_ALBUM, OWN_EP] }) });

    await renderLoaded();

    expect(screen.getByText('Albums')).toBeTruthy();
    expect(screen.getByText('EPs')).toBeTruthy();
  });

  it('a release without a type counts as an album', async () => {
    globalThis.fetch = subsonic({
      artistData: artist({ album: [{ id: 'album-9', name: 'Untyped', artist: 'Angerfist' }] })
    });

    await renderLoaded();

    expect(screen.getByText('Albums')).toBeTruthy();
  });

  it('releases by someone else are listed separately', async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: [OWN_ALBUM, GUEST_ALBUM] }) });

    await renderLoaded();

    expect(screen.getByText('Various Hardcore')).toBeTruthy();
  });

  it('copes with a server that returns a single album rather than a list', async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: OWN_ALBUM }) });

    await renderLoaded();

    expect(screen.getByText('Close Combat')).toBeTruthy();
  });

  it('an artist without releases shows none', async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: undefined }) });

    await renderLoaded();

    expect(screen.queryByText('Close Combat')).toBeNull();
  });

  it('opens the release that was clicked', async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getByText('Close Combat'));

    expect(onnavigate).toHaveBeenCalledWith('album:album-1');
  });

  it('opens a similar artist that was clicked', async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });
    await waitFor(() => expect(screen.getByText('Outsiders')).toBeTruthy());

    await fireEvent.click(screen.getByText('Outsiders'));

    expect(onnavigate).toHaveBeenCalledWith('artist:artist-2');
  });

  it('asks for short tracks in song mode', async () => {
    await renderLoaded();

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('maxDuration=10'))).toBe(true)
    );
  });

  it('asks for long recordings in set mode', async () => {
    viewMode.set('sets');

    await renderLoaded();

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('minDuration=10'))).toBe(true)
    );
  });

  it('asks the server to deduplicate when that is switched on', async () => {
    deduplicateEnabled.set(true);

    await renderLoaded();

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('deduplicate=true'))).toBe(true)
    );
  });

  it('shows the tracks it loaded', async () => {
    await renderLoaded();

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
  });

  it('playing the artist queues their tracks', async () => {
    const { container } = await renderLoaded();
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());

    await fireEvent.click(container.querySelector('.bg-brand.rounded-full'));

    expect(get(currentTrack)).toEqual(TRACK);
    expect(get(playerState).playing).toBe(true);
  });

  it('starring the artist tells the server', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByTitle('Toevoegen aan favorieten'));

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('/rest/star?artistId=artist-1'))).toBe(true)
    );
  });

  it('unstarring an artist that is starred tells the server', async () => {
    globalThis.fetch = subsonic({ artistData: artist({ starred: '2026-01-01T01:00:00Z' }) });
    await renderLoaded();

    await fireEvent.click(screen.getByTitle('Verwijderen uit favorieten'));

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('/rest/unstar?artistId=artist-1'))).toBe(true)
    );
  });

  it('a star the server refuses is rolled back', async () => {
    globalThis.fetch = subsonic({ starOk: false });
    await renderLoaded();

    await fireEvent.click(screen.getByTitle('Toevoegen aan favorieten'));

    await waitFor(() => expect(screen.getByTitle('Toevoegen aan favorieten')).toBeTruthy());
  });

  it('an artist without extra information still renders', async () => {
    globalThis.fetch = subsonic({ info: null });

    await renderLoaded();

    expect(screen.queryByText('Outsiders')).toBeNull();
  });

  it('survives a request that never arrives', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(ArtistView, { artistId: 'artist-1', onnavigate: vi.fn() });

    await waitFor(() => expect(screen.queryByText('Laden...')).toBeNull());
  });
});
