import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import SearchBar from '../../src/lib/SearchBar.svelte';
import { activeView, credentials, currentTrack, playlist, viewMode } from '../../src/lib/store.js';

const TRACK = { id: 'song-1', title: 'Raise Your Fist', artist: 'Angerfist', suffix: 'flac' };

function subsonicApi({ searchResult = {}, genres = ['Hardcore', 'House'], labels = ['Roughstate'] } = {}) {
  return vi.fn(async (url) => {
    if (url.includes('/rest/getGenres')) {
      return { json: async () => ({ 'subsonic-response': { genres: { genre: genres.map((value) => ({ value })) } } }) };
    }
    if (url.includes('/rest/getRecordLabels')) {
      return { json: async () => ({ 'subsonic-response': { recordLabels: { recordLabel: labels } } }) };
    }
    return { json: async () => ({ 'subsonic-response': { searchResult3: searchResult } }) };
  });
}

/** Type into the box and let the 300ms debounce elapse. */
async function search(term) {
  await fireEvent.input(screen.getByRole('textbox'), { target: { value: term } });
  await vi.advanceTimersByTimeAsync(300);
}

describe('SearchBar', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    credentials.set({ url: '', username: 'user', password: 'pw' });
    viewMode.set('songs');
    activeView.set('home');
    currentTrack.set(null);
    playlist.set([]);
    globalThis.fetch = subsonicApi({ searchResult: { song: [TRACK] } });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('loads the genres and labels it filters on locally', async () => {
    render(SearchBar);

    await waitFor(() => {
      const urls = globalThis.fetch.mock.calls.map(([url]) => url);
      expect(urls.some((url) => url.includes('/rest/getGenres'))).toBe(true);
      expect(urls.some((url) => url.includes('/rest/getRecordLabels'))).toBe(true);
    });
  });

  it('shows nothing until something is typed', () => {
    render(SearchBar);

    expect(screen.queryByText('Geen resultaten gevonden.')).toBeNull();
  });

  it('waits for the typing to settle before querying the server', async () => {
    render(SearchBar);
    globalThis.fetch.mockClear();

    await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'ang' } });
    await vi.advanceTimersByTimeAsync(200);
    expect(globalThis.fetch).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(100);
    expect(globalThis.fetch).toHaveBeenCalled();
  });

  it('searches for short tracks in song mode', async () => {
    render(SearchBar);
    await search('angerfist');

    expect(globalThis.fetch.mock.calls.at(-1)[0]).toContain('maxDuration=10');
  });

  it('searches for long recordings in set mode', async () => {
    viewMode.set('sets');
    render(SearchBar);
    await search('angerfist');

    expect(globalThis.fetch.mock.calls.at(-1)[0]).toContain('minDuration=10');
  });

  it('shows the tracks it found', async () => {
    render(SearchBar);
    await search('angerfist');

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
  });

  it('offers the genres and labels that match what was typed', async () => {
    render(SearchBar);
    await search('hard');

    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());
    expect(screen.queryByText('House')).toBeNull();
  });

  it('says so when a search turns up nothing', async () => {
    globalThis.fetch = subsonicApi({ searchResult: {} });
    render(SearchBar);
    await search('zzzz');

    await waitFor(() => expect(screen.getByText('Geen resultaten gevonden.')).toBeTruthy());
  });

  it('clearing the box drops the results without another request', async () => {
    render(SearchBar);
    await search('angerfist');
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
    globalThis.fetch.mockClear();

    await fireEvent.input(screen.getByRole('textbox'), { target: { value: '' } });
    await vi.advanceTimersByTimeAsync(300);

    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });

  it('plays the track that was picked and puts it at the front of the queue', async () => {
    render(SearchBar);
    await search('angerfist');
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());

    await fireEvent.click(screen.getByText('Raise Your Fist'));

    expect(get(currentTrack)).toEqual(TRACK);
    expect(get(playlist)).toEqual([TRACK]);
  });

  it('does not queue the same track twice', async () => {
    playlist.set([TRACK]);
    render(SearchBar);
    await search('angerfist');
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());

    await fireEvent.click(screen.getByText('Raise Your Fist'));

    expect(get(playlist)).toEqual([TRACK]);
  });

  it('opens the artist that was picked', async () => {
    globalThis.fetch = subsonicApi({ searchResult: { artist: [{ id: 'artist-1', name: 'Angerfist' }] } });
    render(SearchBar);
    await search('angerfist');
    await waitFor(() => expect(screen.getByText('Angerfist')).toBeTruthy());

    await fireEvent.click(screen.getByText('Angerfist'));

    expect(get(activeView)).toBe('artist:artist-1');
  });

  it('opens the album that was picked', async () => {
    globalThis.fetch = subsonicApi({ searchResult: { album: [{ id: 'album-1', name: 'Close Combat', artist: 'Angerfist' }] } });
    render(SearchBar);
    await search('close');
    await waitFor(() => expect(screen.getByText('Close Combat')).toBeTruthy());

    await fireEvent.click(screen.getByText('Close Combat'));

    expect(get(activeView)).toBe('album:album-1');
  });

  it('opens the genre that was picked', async () => {
    globalThis.fetch = subsonicApi({ searchResult: {} });
    render(SearchBar);
    await search('hard');
    await waitFor(() => expect(screen.getByText('Hardcore')).toBeTruthy());

    await fireEvent.click(screen.getByText('Hardcore'));

    expect(get(activeView)).toBe('genre:Hardcore');
  });

  it('opens the label that was picked', async () => {
    globalThis.fetch = subsonicApi({ searchResult: {} });
    render(SearchBar);
    await search('rough');
    await waitFor(() => expect(screen.getByText('Roughstate')).toBeTruthy());

    await fireEvent.click(screen.getByText('Roughstate'));

    expect(get(activeView)).toBe('label:Roughstate');
  });

  it('closes the results shortly after the box loses focus', async () => {
    render(SearchBar);
    await search('angerfist');
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());

    await fireEvent.blur(screen.getByRole('textbox'));
    await vi.advanceTimersByTimeAsync(200);

    expect(screen.queryByText('Raise Your Fist')).toBeNull();
  });

  it('re-runs the search when the view mode changes under it', async () => {
    render(SearchBar);
    await search('angerfist');
    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
    globalThis.fetch.mockClear();

    viewMode.set('sets');
    await vi.advanceTimersByTimeAsync(0);

    await waitFor(() => expect(globalThis.fetch.mock.calls.at(-1)[0]).toContain('minDuration=10'));
  });

  it('survives a search request that fails', async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes('/rest/search3')) throw new Error('network down');
      return { json: async () => ({ 'subsonic-response': {} }) };
    });
    render(SearchBar);

    await search('angerfist');

    expect(screen.getByRole('textbox').value).toBe('angerfist');
  });

  it('survives a genre list that fails to load', async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes('/rest/getGenres')) throw new Error('network down');
      return { json: async () => ({ 'subsonic-response': { searchResult3: { song: [TRACK] } } }) };
    });
    render(SearchBar);

    await search('angerfist');

    await waitFor(() => expect(screen.getByText('Raise Your Fist')).toBeTruthy());
  });
});
