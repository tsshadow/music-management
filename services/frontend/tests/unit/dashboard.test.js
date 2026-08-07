import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Dashboard from '../../src/lib/Dashboard.svelte';
import {
  credentials, deduplicateEnabled, favoriteGenres, favoriteLabels, favoritePlaylists,
  memoriesOnHomeEnabled, viewMode
} from '../../src/lib/store.js';

const TRACK = { id: 'song-1', title: 'Raise Your Fist', artist: 'Angerfist', artistId: 'artist-1', duration: 240, suffix: 'flac' };
const ALBUM = { id: 'album-1', name: 'Close Combat', artist: 'Angerfist', artistId: 'artist-1' };
const ARTIST = { id: 'artist-1', name: 'Angerfist' };
const PLAYLIST = { id: 'pl-1', name: 'Gabber', songCount: 12 };

/** Answers every endpoint the home screen and its list views touch. */
function subsonic({
  curated = [TRACK],
  tracks = { track: [TRACK], moreResults: false, nextOffset: 1 },
  albums = [ALBUM],
  artists = [ARTIST],
  playlists = [PLAYLIST],
  genres = [{ value: 'Hardcore', songCount: 1200 }],
  labels = [{ value: 'Roughstate', albumCount: 20 }],
  memories = null
} = {}) {
  return vi.fn(async (url) => {
    if (url.includes('/rest/getSpotifyPlaylist')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { playlist: { entry: curated } } }) };
    }
    if (url.includes('/rest/getSpotifyTracks')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { tracks } }) };
    }
    if (url.includes('/rest/getAlbumList2')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { albumList2: { album: albums } } }) };
    }
    if (url.includes('/rest/getArtistList')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { artistList: { artist: artists } } }) };
    }
    if (url.includes('/rest/getPlaylists')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { playlists: { playlist: playlists } } }) };
    }
    if (url.includes('/rest/getGenres')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { genres: { genre: genres } } }) };
    }
    if (url.includes('/rest/getRecordLabels')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { recordLabels: { recordLabel: labels } } }) };
    }
    if (url.includes('/rest/getMemories')) {
      if (memories === null) return { ok: false, json: async () => ({}) };
      return { ok: true, json: async () => memories };
    }
    return { ok: true, json: async () => ({ 'subsonic-response': { status: 'ok' } }) };
  });
}

function urlsFor(fragment) {
  return globalThis.fetch.mock.calls.map(([url]) => url).filter((url) => url.includes(fragment));
}

describe('Dashboard', () => {
  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    viewMode.set('songs');
    deduplicateEnabled.set(false);
    favoriteGenres.set([]);
    memoriesOnHomeEnabled.set(false);
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the curated rows on the home screen', async () => {
    render(Dashboard, { activeView: 'home' });

    await waitFor(() => expect(screen.getAllByText('Raise Your Fist').length).toBeGreaterThan(0));
    expect(urlsFor('/rest/getSpotifyPlaylist')).toHaveLength(3);
  });

  it('the memories row stays away when it is switched off', async () => {
    render(Dashboard, { activeView: 'home' });

    await waitFor(() => expect(screen.getAllByText('Raise Your Fist').length).toBeGreaterThan(0));
    expect(urlsFor('/rest/getMemories')).toHaveLength(0);
  });

  it('the memories row is loaded when it is switched on', async () => {
    memoriesOnHomeEnabled.set(true);

    render(Dashboard, { activeView: 'home' });

    await waitFor(() => expect(urlsFor('/rest/getMemories').length).toBeGreaterThan(0));
  });

  it('a server that does not know about memories simply shows none', async () => {
    memoriesOnHomeEnabled.set(true);
    render(Dashboard, { activeView: 'home' });

    await waitFor(() => expect(urlsFor('/rest/getMemories').length).toBeGreaterThan(0));

    // No error banner: an absent memories row is better than one on the home screen.
    expect(screen.queryByText(/Fout/i)).toBeNull();
  });

  it('the songs view loads the track list', async () => {
    render(Dashboard, { activeView: 'songs' });

    await waitFor(() => expect(urlsFor('/rest/getSpotifyTracks').length).toBeGreaterThan(0));
    expect(urlsFor('/rest/getSpotifyTracks')[0]).toContain('maxDuration=10');
  });

  it('the sets view asks for long recordings', async () => {
    viewMode.set('sets');

    render(Dashboard, { activeView: 'sets' });

    await waitFor(() =>
      expect(urlsFor('/rest/getSpotifyTracks').some((url) => url.includes('minDuration=10'))).toBe(true)
    );
  });

  it('a genre view filters on that genre', async () => {
    render(Dashboard, { activeView: 'genre:Hardcore' });

    await waitFor(() =>
      expect(urlsFor('/rest/getSpotifyTracks').some((url) => url.includes('genre=Hardcore'))).toBe(true)
    );
  });

  it('a label view filters on that label', async () => {
    render(Dashboard, { activeView: 'label:Roughstate' });

    await waitFor(() =>
      expect(urlsFor('/rest/getSpotifyTracks').some((url) => url.includes('label=Roughstate'))).toBe(true)
    );
  });

  it('asks the server to deduplicate when that is switched on', async () => {
    deduplicateEnabled.set(true);

    render(Dashboard, { activeView: 'songs' });

    await waitFor(() =>
      expect(urlsFor('/rest/getSpotifyTracks').some((url) => url.includes('deduplicate=true'))).toBe(true)
    );
  });

  it('the albums view lists the albums', async () => {
    render(Dashboard, { activeView: 'albums' });

    await waitFor(() => expect(screen.getByText('Close Combat')).toBeTruthy());
  });

  it('the artists view lists the artists', async () => {
    render(Dashboard, { activeView: 'artists' });

    await waitFor(() => expect(screen.getByText('Angerfist')).toBeTruthy());
  });

  it('the playlists view lists the playlists', async () => {
    render(Dashboard, { activeView: 'playlists' });

    await waitFor(() => expect(screen.getByText('Gabber')).toBeTruthy());
  });

  it('the genres view lists the genres', async () => {
    render(Dashboard, { activeView: 'genres' });

    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());
  });

  it('a genre can be marked as a favourite', async () => {
    render(Dashboard, { activeView: 'genres' });
    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());

    await fireEvent.click(screen.getAllByLabelText('Favoriet toggelen')[0]);

    expect(get(favoriteGenres)).toContain('Hardcore');
  });

  it('the labels view lists the labels', async () => {
    render(Dashboard, { activeView: 'labels' });

    await waitFor(() => expect(screen.getByText('Roughstate')).toBeTruthy());
  });

  it('an artist view is handed to the artist screen', async () => {
    render(Dashboard, { activeView: 'artist:artist-1' });

    await waitFor(() =>
      expect(urlsFor('/rest/getArtist?').some((url) => url.includes('id=artist-1'))).toBe(true)
    );
  });

  it('an album view is handed to the album screen', async () => {
    render(Dashboard, { activeView: 'album:album-1' });

    await waitFor(() =>
      expect(urlsFor('/rest/getAlbum?').some((url) => url.includes('id=album-1'))).toBe(true)
    );
  });

  it('the starred view is reachable', async () => {
    render(Dashboard, { activeView: 'starred' });

    await waitFor(() => expect(urlsFor('/rest/getStarred2').length).toBeGreaterThan(0));
  });

  it('survives a server that answers nothing useful', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(Dashboard, { activeView: 'home' });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
  });

  it('keeps a colon inside a label name instead of filtering on half of it', async () => {
    render(Dashboard, { activeView: 'label:Kompakt: Total' });

    await waitFor(() =>
      expect(urlsFor('/rest/getSpotifyTracks').some((url) => url.includes(`label=${encodeURIComponent('Kompakt: Total')}`))).toBe(true)
    );
  });

  it('does not carry a search term over into the label that was tapped next', async () => {
    const { rerender } = render(Dashboard, { activeView: 'search:Angerfist' });
    await waitFor(() => expect(urlsFor('query=Angerfist').length).toBeGreaterThan(0));

    await rerender({ activeView: 'label:Roughstate' });

    await waitFor(() => expect(urlsFor('label=Roughstate').length).toBeGreaterThan(0));
    expect(urlsFor('label=Roughstate').every((url) => !url.includes('query='))).toBe(true);
  });
});

describe('Dashboard - collection sorting and filtering', () => {
  const GENRES = [
    { value: 'Hardcore', songCount: 1200, albumCount: 90 },
    { value: 'Ambient', songCount: 400, albumCount: 30 },
    { value: 'Mistag', songCount: 2, albumCount: 1 }
  ];
  const LABELS = [
    { value: 'Roughstate', songCount: 500, albumCount: 20 },
    { value: 'Anjunadeep', songCount: 120, albumCount: 8 }
  ];
  const PLAYLISTS = [
    { id: 'pl-1', name: 'Gabber', songCount: 12, duration: 2400, owner: 'user', public: false },
    { id: 'pl-2', name: 'Chill', songCount: 300, duration: 36000, owner: 'gast', public: 'true' }
  ];

  /** The names on the cards, in the order they are rendered. */
  function cardNames(candidates) {
    return candidates.filter((name) => screen.queryByText(name)).sort(
      (a, b) =>
        screen.getByText(a).compareDocumentPosition(screen.getByText(b)) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
    );
  }

  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    viewMode.set('songs');
    deduplicateEnabled.set(false);
    favoriteGenres.set([]);
    favoriteLabels.set([]);
    favoritePlaylists.set([]);
    memoriesOnHomeEnabled.set(false);
    globalThis.fetch = subsonic({ genres: GENRES, labels: LABELS, playlists: PLAYLISTS });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hides the long tail of tiny genres by default, and shows it on request', async () => {
    render(Dashboard, { activeView: 'genres' });
    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());

    expect(screen.queryByText('Mistag')).toBeNull();

    await fireEvent.click(screen.getByRole('button', { name: 'Alles' }));

    await waitFor(() => expect(screen.getByText('Mistag')).toBeTruthy());
  });

  it('searches genres by name, ignoring case', async () => {
    render(Dashboard, { activeView: 'genres' });
    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());

    await fireEvent.input(screen.getByLabelText('Zoeken in deze lijst'), { target: { value: 'ambi' } });

    await waitFor(() => expect(screen.queryByText('Hardcore')).toBeNull());
    expect(screen.getByText('Ambient')).toBeTruthy();
  });

  it('sorts genres by track count, most first', async () => {
    render(Dashboard, { activeView: 'genres' });
    await waitFor(() => expect(screen.getByText('Ambient')).toBeTruthy());

    await fireEvent.change(screen.getByLabelText('Sorteer op'), { target: { value: 'songs' } });

    await waitFor(() => expect(cardNames(['Hardcore', 'Ambient'])).toEqual(['Hardcore', 'Ambient']));
  });

  it('offers a way back when the filters match nothing', async () => {
    render(Dashboard, { activeView: 'genres' });
    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());

    await fireEvent.input(screen.getByLabelText('Zoeken in deze lijst'), { target: { value: 'niets' } });
    await waitFor(() => expect(screen.getByText('Niets voldoet aan deze filters')).toBeTruthy());

    await fireEvent.click(screen.getByRole('button', { name: 'Filters wissen' }));

    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());
  });

  it('marks a label as favourite and can then show only those', async () => {
    render(Dashboard, { activeView: 'labels' });
    await waitFor(() => expect(screen.getByText('Roughstate')).toBeTruthy());

    // The grid starts alphabetical, so the first heart belongs to Anjunadeep.
    await fireEvent.click(screen.getAllByLabelText('Favoriet label toggelen')[0]);
    expect(get(favoriteLabels)).toEqual(['Anjunadeep']);

    await fireEvent.click(screen.getByRole('button', { name: /Favorieten/ }));

    await waitFor(() => expect(screen.queryByText('Roughstate')).toBeNull());
    expect(screen.getByText('Anjunadeep')).toBeTruthy();
  });

  it('shows how many tracks a label holds', async () => {
    render(Dashboard, { activeView: 'labels' });

    await waitFor(() => expect(screen.getByText(/500 nummers/)).toBeTruthy());
  });

  it('filters playlists down to the ones you own', async () => {
    render(Dashboard, { activeView: 'playlists' });
    await waitFor(() => expect(screen.getByText('Chill')).toBeTruthy());

    await fireEvent.click(screen.getByRole('button', { name: 'Van mij' }));

    await waitFor(() => expect(screen.queryByText('Chill')).toBeNull());
    expect(screen.getByText('Gabber')).toBeTruthy();
  });

  it('sorts playlists by length', async () => {
    render(Dashboard, { activeView: 'playlists' });
    await waitFor(() => expect(screen.getByText('Gabber')).toBeTruthy());

    await fireEvent.change(screen.getByLabelText('Sorteer op'), { target: { value: 'duration' } });

    await waitFor(() => expect(cardNames(['Chill', 'Gabber'])).toEqual(['Chill', 'Gabber']));
  });
});
