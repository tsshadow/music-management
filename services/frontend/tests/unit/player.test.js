import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Player from '../../src/lib/Player.svelte';
import {
  credentials, currentTrack, isMobile, playerState, playlist, radioChannel, syncMode
} from '../../src/lib/store.js';

const FIRST = { id: 'song-1', title: 'Raise Your Fist', artist: 'Angerfist', artistId: 'artist-1', albumId: 'album-1', duration: 240 };
const SECOND = { id: 'song-2', title: 'Encore', artist: 'Angerfist', artistId: 'artist-1', albumId: 'album-1', duration: 200 };

function api() {
  return vi.fn(async () => ({ ok: true, json: async () => ({ 'subsonic-response': { status: 'ok' } }) }));
}

function renderPlayer(props = {}) {
  return render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn(), ...props });
}

describe('Player', () => {
  beforeEach(() => {
    credentials.set({ url: '', username: 'user', password: 'pw' });
    playlist.set([FIRST, SECOND]);
    currentTrack.set(FIRST);
    playerState.set({ playing: false, repeat: 'none', shuffle: false, volume: 50 });
    syncMode.set('off');
    radioChannel.set(null);
    isMobile.set(false);
    globalThis.fetch = api();
    // jsdom has no real audio pipeline.
    window.HTMLMediaElement.prototype.play = vi.fn(async () => {});
    window.HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the track that is playing', () => {
    renderPlayer();

    expect(screen.getAllByText('Raise Your Fist').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Angerfist').length).toBeGreaterThan(0);
  });

  it('nothing is shown without a track', () => {
    currentTrack.set(null);

    renderPlayer();

    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });

  it('the play button asks the audio element to play', async () => {
    // Only the mobile transport labels its play button.
    isMobile.set(true);
    renderPlayer();

    await fireEvent.click(screen.getByLabelText('Afspelen'));

    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it('the state follows what the audio element reports', async () => {
    // togglePlay drives the element; the store is updated by its play/pause
    // events, which is what an OS media key or a car head unit triggers too.
    const { container } = renderPlayer();
    const audioElement = container.querySelector('audio');

    await fireEvent.play(audioElement);
    expect(get(playerState).playing).toBe(true);

    await fireEvent.pause(audioElement);
    expect(get(playerState).playing).toBe(false);
  });

  it('next moves to the following track', async () => {
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText('Volgende')[0]);

    expect(get(currentTrack)).toEqual(SECOND);
  });

  it('next stops at the end of the queue', async () => {
    currentTrack.set(SECOND);
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText('Volgende')[0]);

    expect(get(currentTrack)).toEqual(SECOND);
  });

  it('next wraps around when everything repeats', async () => {
    currentTrack.set(SECOND);
    playerState.update((s) => ({ ...s, repeat: 'all' }));
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText('Volgende')[0]);

    expect(get(currentTrack)).toEqual(FIRST);
  });

  it('next picks another track when shuffling', async () => {
    playerState.update((s) => ({ ...s, shuffle: true }));
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText('Volgende')[0]);

    expect(get(currentTrack)).toEqual(SECOND);
  });

  it('previous moves back a track', async () => {
    currentTrack.set(SECOND);
    renderPlayer();

    await fireEvent.click(screen.getByLabelText('Vorige'));

    expect(get(currentTrack)).toEqual(FIRST);
  });

  it('the repeat button cycles through its modes', async () => {
    renderPlayer();
    const repeat = screen.getByLabelText('Herhalen');

    await fireEvent.click(repeat);
    expect(get(playerState).repeat).toBe('all');

    await fireEvent.click(repeat);
    expect(get(playerState).repeat).toBe('one');

    await fireEvent.click(repeat);
    expect(get(playerState).repeat).toBe('none');
  });

  it('the shuffle button toggles shuffling', async () => {
    renderPlayer();

    await fireEvent.click(screen.getByLabelText('Shuffle'));

    expect(get(playerState).shuffle).toBe(true);
  });

  it('the queue button is handed back to the parent', async () => {
    const ontoggleQueue = vi.fn();
    renderPlayer({ ontoggleQueue });

    await fireEvent.click(screen.getByLabelText('Wachtrij'));

    expect(ontoggleQueue).toHaveBeenCalled();
  });

  it('an empty queue has nothing to skip to', async () => {
    playlist.set([]);
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText('Volgende')[0]);

    expect(get(currentTrack)).toEqual(FIRST);
  });

  it('rating the track tells the server', async () => {
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText('4 sterren')[0]);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('/rest/setRating'))).toBe(true)
    );
  });

  it('the album of the track can be opened', async () => {
    const onnavigate = vi.fn();
    renderPlayer({ onnavigate });

    await fireEvent.click(screen.getAllByText('Raise Your Fist')[0]);

    expect(onnavigate).toHaveBeenCalledWith('album:album-1');
  });

  it('the artist of the track can be opened', async () => {
    const onnavigate = vi.fn();
    renderPlayer({ onnavigate });

    await fireEvent.click(screen.getAllByText('Angerfist')[0]);

    expect(onnavigate).toHaveBeenCalledWith('artist:artist-1');
  });
});
