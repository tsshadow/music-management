import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import History from '../../src/lib/History.svelte';
import MemoriesView from '../../src/lib/MemoriesView.svelte';
import MemoriesYearView from '../../src/lib/MemoriesYearView.svelte';
import PlaylistView from '../../src/lib/PlaylistView.svelte';
import {
  credentials, currentPlaylist, currentTrack, playerState, playlist
} from '../../src/lib/store.js';

const TRACK = { id: 'song-1', title: 'Raise Your Fist', artist: 'Angerfist', artistId: 'artist-1', suffix: 'flac' };
const SECOND = { id: 'song-2', title: 'Encore', artist: 'Angerfist', artistId: 'artist-1', suffix: 'flac' };

function resetPlayer() {
  credentials.set({ url: '', username: 'user', password: 'pw' });
  playlist.set([]);
  currentTrack.set(null);
  playerState.set({ playing: false });
}

describe('History', () => {
  beforeEach(() => {
    resetPlayer();
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        'subsonic-response': { history: { entry: [{ ...TRACK, listenedAt: '2026-01-01T01:00:00Z' }] } }
      })
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists what was listened to', async () => {
    render(History, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/rest/getSpotifyHistory');
  });

  it('copes with a server that returns a single entry rather than a list', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ 'subsonic-response': { history: { entry: { ...TRACK, listenedAt: '2026-01-01T01:00:00Z' } } } })
    }));

    render(History, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
  });

  it('survives a request that never arrives', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(History, { onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });

  it('an empty history shows nothing', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true, json: async () => ({ 'subsonic-response': { history: { entry: [] } } })
    }));

    render(History, { onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });
});

describe('PlaylistView', () => {
  beforeEach(() => {
    resetPlayer();
    currentPlaylist.set({ id: 'pl-1', name: 'Gabber' });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        'subsonic-response': { playlist: { id: 'pl-1', name: 'Gabber', entry: [TRACK, SECOND] } }
      })
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the tracks of the playlist', async () => {
    render(PlaylistView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/rest/getPlaylist?id=pl-1');
  });

  it('copes with a playlist holding a single track', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ 'subsonic-response': { playlist: { id: 'pl-1', name: 'Gabber', entry: TRACK } } })
    }));

    render(PlaylistView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
  });

  it('playing the playlist queues it and starts the first track', async () => {
    const { container } = render(PlaylistView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());

    await fireEvent.click(container.querySelector('.bg-brand'));

    expect(get(playlist)).toHaveLength(2);
    expect(get(currentTrack)).toEqual(TRACK);
    expect(get(playerState).playing).toBe(true);
  });

  it('survives a request that never arrives', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(PlaylistView, { onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });
});

describe('MemoriesView', () => {
  const MEMORIES = {
    'subsonic-response': {
      memories: {
        memory: [
          { year: 2024, song: [TRACK] },
          { year: 2023, song: [SECOND] }
        ]
      }
    }
  };

  beforeEach(() => {
    resetPlayer();
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => MEMORIES }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('groups what was listened to on this day per year', async () => {
    render(MemoriesView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
    expect(screen.getByText('Encore')).toBeTruthy();
    expect(globalThis.fetch.mock.calls[0][0]).toContain('/rest/getMemories');
  });

  it('playing a year queues the whole year, not the handful on the tile', async () => {
    // The overview holds a short page per year, so the play button has to go and get the rest
    // before it queues anything.
    const wholeYear = Array.from({ length: 40 }, (_, i) => ({ ...TRACK, id: `y-${i}`, title: `Year track ${i}` }));
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () =>
        String(url).includes('year=2024')
          ? { 'subsonic-response': { memories: { memory: [{ year: 2024, song: wholeYear }] } } }
          : MEMORIES
    }));

    const { container } = render(MemoriesView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());

    await fireEvent.click(container.querySelectorAll('.bg-brand')[0]);

    await waitFor(() => expect(get(playlist)).toHaveLength(40));
    expect(get(currentTrack).id).toBe('y-0');
    expect(get(playerState).playing).toBe(true);
  });

  it('survives a server that does not know about memories', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));

    render(MemoriesView, { onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });

  it('survives a request that never arrives', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(MemoriesView, { onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });

  it('asks for a short page per year, since the server ranks and counts them', async () => {
    render(MemoriesView, { onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(globalThis.fetch.mock.calls[0][0]).toContain('maxPerYear=12');
    expect(globalThis.fetch.mock.calls[0][0]).not.toContain('year=');
  });

  it('shows one tile per year, with the year and its size', async () => {
    render(MemoriesView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('2024')).toBeTruthy());
    expect(screen.getByText('2023')).toBeTruthy();
    expect(screen.getAllByText('1 nummer')).toHaveLength(2);
  });

  it('draws a year whose best tracks share one sleeve', async () => {
    // Real libraries do this constantly: the top tracks of a year come off the same album, so the
    // tile's covers repeat. Keying anything on the cover id turns that into a render error, and the
    // whole screen goes blank rather than one tile looking dull.
    const sameAlbum = (id) => ({ ...TRACK, id, title: `Track ${id}`, coverArt: 'art-1', playCount: 5 });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        'subsonic-response': {
          memories: {
            memory: [
              {
                year: 2025,
                yearsAgo: 1,
                exact: true,
                song: [sameAlbum('s1'), sameAlbum('s2'), sameAlbum('s3'), sameAlbum('s4')]
              }
            ]
          }
        }
      })
    }));

    render(MemoriesView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('2025')).toBeTruthy());
    expect(screen.getByText('4 nummers')).toBeTruthy();
  });

  it('opening a tile navigates to that year', async () => {
    const onnavigate = vi.fn();
    render(MemoriesView, { onnavigate });

    await waitFor(() => expect(screen.getByText('2024')).toBeTruthy());
    await fireEvent.click(screen.getByLabelText('2024 openen'));

    expect(onnavigate).toHaveBeenCalledWith('memories:2024');
  });
});

describe('MemoriesYearView', () => {
  const yearOf = (count) => ({
    'subsonic-response': {
      memories: {
        memory: [
          {
            year: 2025,
            yearsAgo: 1,
            exact: true,
            song: Array.from({ length: count }, (_, i) => ({ ...TRACK, id: `song-${i}`, title: `Track ${i}` }))
          }
        ]
      }
    }
  });

  beforeEach(() => {
    resetPlayer();
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => yearOf(60) }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the first fifty tracks and keeps the rest behind a button', async () => {
    render(MemoriesYearView, { year: '2025', onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Track 0')).toBeTruthy());
    expect(screen.queryByText('Track 49')).toBeTruthy();
    expect(screen.queryByText('Track 50')).toBeNull();
    expect(screen.getByText('Meer laden')).toBeTruthy();
  });

  it('load more reveals the next fifty and then retires itself', async () => {
    render(MemoriesYearView, { year: '2025', onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText('Track 0')).toBeTruthy());

    await fireEvent.click(screen.getByText('Meer laden'));

    await waitFor(() => expect(screen.getByText('Track 59')).toBeTruthy());
    expect(screen.queryByText('Meer laden')).toBeNull();
  });

  it('counts the whole year, not just what is on screen', async () => {
    render(MemoriesYearView, { year: '2025', onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/60 nummers/)).toBeTruthy());
  });

  it('plays the whole year rather than the visible page', async () => {
    const { container } = render(MemoriesYearView, { year: '2025', onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText('Track 0')).toBeTruthy());

    await fireEvent.click(container.querySelector('.bg-brand'));

    expect(get(playlist)).toHaveLength(60);
    expect(get(playerState).playing).toBe(true);
  });

  it('says so when today holds no memories from that year', async () => {
    render(MemoriesYearView, { year: '1999', onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText('Vandaag geen memories uit 1999.')).toBeTruthy());
  });

  it('goes back to the overview', async () => {
    const onnavigate = vi.fn();
    render(MemoriesYearView, { year: '2025', onnavigate });

    await fireEvent.click(screen.getByText('Alle jaren'));

    expect(onnavigate).toHaveBeenCalledWith('memories');
  });
});
