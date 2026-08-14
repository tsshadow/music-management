import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import Player from '../../src/lib/Player.svelte';
import {
  credentials, currentTrack, isMobile, playerState, playlist, radioChannel, syncMode
} from '../../src/lib/store.js';
import { notify, dismissAll } from '../../src/lib/notifications.js';

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
    // The store outlives a render, so a notification raised here would show
    // up in the next test's assertions.
    dismissAll();
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

  it('reports a rejected rating and puts the old one back', async () => {
    const spy = vi.spyOn(notify, 'error');
    // Subsonic rejects with a 200, which is exactly what used to pass as a
    // success here.
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        'subsonic-response': { status: 'failed', error: { code: 50, message: 'Not authorized' } },
      }),
    }));
    currentTrack.set({ ...FIRST, userRating: 3 });
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText('5 sterren')[0]);

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][0]).toBe('Beoordeling kon niet worden opgeslagen');
    expect(get(currentTrack).userRating).toBe(3);
  });

  // Losing a scrobble does not stop the music, so it must not read as an
  // error the user has to act on.
  it('reports a failed scrobble as a warning, not an error', async () => {
    const warning = vi.spyOn(notify, 'warning');
    const error = vi.spyOn(notify, 'error');
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    });
    const { container } = renderPlayer();

    await fireEvent.play(container.querySelector('audio'));

    await waitFor(() => expect(warning).toHaveBeenCalledWith('Scrobble mislukt', expect.anything()));
    expect(error).not.toHaveBeenCalled();
  });

  it('reports a stream that will not load', async () => {
    const spy = vi.spyOn(notify, 'error');
    const { container } = renderPlayer();

    await fireEvent.error(container.querySelector('audio'));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('"Raise Your Fist" kon niet worden geladen'),
    );
  });

  it('the album of the track can be opened', async () => {
    const onnavigate = vi.fn();
    renderPlayer({ onnavigate });

    await fireEvent.click(screen.getAllByText('Raise Your Fist')[0]);

    expect(onnavigate).toHaveBeenCalledWith('album:album-1');
  });

  it('the progress is followed while the track plays', async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector('audio');
    Object.defineProperty(audioElement, 'currentTime', { value: 30, writable: true });
    Object.defineProperty(audioElement, 'duration', { value: 240, writable: true });

    await fireEvent.timeUpdate(audioElement);

    expect(get(playerState).progress).toBe(30);
  });

  it('the duration is taken from the loaded track', async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector('audio');
    Object.defineProperty(audioElement, 'duration', { value: 240, writable: true });

    await fireEvent.loadedMetadata(audioElement);

    expect(get(playerState).duration).toBe(240);
  });

  it('seeking moves to the clicked position', async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector('audio');
    Object.defineProperty(audioElement, 'duration', { value: 200, writable: true });
    const bar = screen.getByLabelText('Door nummer spoelen');
    bar.getBoundingClientRect = () => ({ left: 0, width: 100 });

    await fireEvent.click(bar, { clientX: 50 });

    expect(audioElement.currentTime).toBe(100);
  });

  it('the volume bar sets the volume', async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector('audio');
    const bar = screen.getByLabelText('Volume');
    bar.getBoundingClientRect = () => ({ left: 0, width: 100 });

    await fireEvent.click(bar, { clientX: 25 });

    expect(audioElement.volume).toBeCloseTo(0.25);
  });

  it('dragging the volume to zero mutes', async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector('audio');
    const bar = screen.getByLabelText('Volume');
    bar.getBoundingClientRect = () => ({ left: 0, width: 100 });

    await fireEvent.click(bar, { clientX: 0 });

    expect(audioElement.volume).toBe(0);
  });

  it('the artist of the track can be opened', async () => {
    const onnavigate = vi.fn();
    renderPlayer({ onnavigate });

    await fireEvent.click(screen.getAllByText('Angerfist')[0]);

    expect(onnavigate).toHaveBeenCalledWith('artist:artist-1');
  });

  describe('radio channels', () => {
    function radioApi(channels) {
      return vi.fn(async (url) => {
        if (url.includes('/api/radio/channels')) return { ok: true, json: async () => ({ channels }) };
        if (url.includes('/api/radio/time')) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        if (url.includes('/state')) return { ok: true, json: async () => ({ current: null, next: null }) };
        return { ok: true, json: async () => ({ 'subsonic-response': { status: 'ok' } }) };
      });
    }

    it('offers a choice when more than one channel is on air', async () => {
      globalThis.fetch = radioApi([
        { slug: 'main', name: 'Radio', filter: {} },
        { slug: 'qdance', name: 'Q-dance', filter: { label: 'Q-dance Records' } }
      ]);
      renderPlayer();

      await fireEvent.click(screen.getByLabelText('Radio'));

      await waitFor(() => expect(screen.getByText('Q-dance')).toBeTruthy());
      expect(screen.getByText('Q-dance Records')).toBeTruthy();
      // Nothing is tuned in until a channel is picked.
      expect(get(radioChannel)).toBeNull();
    });

    it('tunes into the channel that was picked', async () => {
      globalThis.fetch = radioApi([
        { slug: 'main', name: 'Radio', filter: {} },
        { slug: 'qdance', name: 'Q-dance', filter: { label: 'Q-dance Records' } }
      ]);
      renderPlayer();

      await fireEvent.click(screen.getByLabelText('Radio'));
      await waitFor(() => expect(screen.getByText('Q-dance')).toBeTruthy());
      await fireEvent.click(screen.getByText('Q-dance'));

      await waitFor(() => expect(get(radioChannel)).toBe('qdance'));
    });

    it('starts straight away when there is only one channel', async () => {
      globalThis.fetch = radioApi([{ slug: 'main', name: 'Radio', filter: {} }]);
      renderPlayer();

      await fireEvent.click(screen.getByLabelText('Radio'));

      await waitFor(() => expect(get(radioChannel)).toBe('main'));
    });
  });
});
