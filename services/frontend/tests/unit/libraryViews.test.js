import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import History from '../../src/lib/History.svelte';
import MemoriesView from '../../src/lib/MemoriesView.svelte';
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

  it('playing a year queues that group', async () => {
    const { container } = render(MemoriesView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());

    await fireEvent.click(container.querySelectorAll('.bg-brand')[0]);

    expect(get(currentTrack)).toEqual(TRACK);
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
});
