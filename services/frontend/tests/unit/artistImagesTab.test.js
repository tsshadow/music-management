import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import ArtistImagesTab from '../../src/lib/management/tabs/ArtistImagesTab.svelte';

const DAFT_PUNK = {
  id: 28151, name: 'Daft Punk', primary_image_id: 11431, has_image: true, image_status: 'active',
  image_updated_at: '2026-01-01T00:00:00', width: 640, height: 640, mime_type: 'image/jpeg',
  file_size: 1000, source: 'spotify', original_url: null
};
const NO_IMAGE = {
  id: 47776, name: 'HARD TECHNO Daft Punk', primary_image_id: null, has_image: false,
  image_status: 'failed', image_updated_at: null, width: null, height: null, mime_type: null,
  file_size: null, source: null, original_url: null
};

function baseProps(overrides = {}) {
  return {
    API_BASE: '/muma',
    apiKey: 'k',
    getHeaders: (extra = {}) => ({ ...extra, 'X-API-Key': 'k' }),
    fetchArtistImages: () => {},
    fetchProgress: { active: false, total: 0, current: 0, last_artist: null, status: 'idle' },
    imageStats: { total_artists: 2, artists_with_images: 1, artists_without_images: 1 },
    refreshStats: () => {},
    onMessage: () => {},
    onError: () => {},
    ...overrides
  };
}

function mockSearch(items, total = items.length) {
  return vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => ({ items, total, limit: 60, offset: 0 })
  }));
}

describe('ArtistImagesTab', () => {
  beforeEach(() => {
    globalThis.fetch = mockSearch([DAFT_PUNK, NO_IMAGE]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists artists on first render, with and without an image', async () => {
    render(ArtistImagesTab, baseProps());

    await waitFor(() => expect(screen.getByText('Daft Punk')).toBeTruthy());
    // An artist without an image must be listed too -- it is exactly the one you
    // need to find in order to give it an image.
    expect(screen.getByText('HARD TECHNO Daft Punk')).toBeTruthy();
  });

  it('shows the image of a found artist', async () => {
    render(ArtistImagesTab, baseProps());

    const img = await screen.findByAltText('Daft Punk');
    expect(img.getAttribute('src')).toContain('/muma/api/artists/Daft%20Punk/image');
    expect(img.getAttribute('src')).toContain('apiKey=k');
  });

  it('sends the typed query url-encoded after debouncing', async () => {
    render(ArtistImagesTab, baseProps());
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    globalThis.fetch.mockClear();

    const input = screen.getByPlaceholderText('Zoek artiest...');
    await fireEvent.input(input, { target: { value: 'daft & punk' } });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled(), { timeout: 2000 });
    const urls = globalThis.fetch.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('q=daft+%26+punk'))).toBe(true);
    expect(urls.some((u) => u.includes('/api/artists/manage/search'))).toBe(true);
  });

  it('surfaces a failing search instead of silently rendering nothing', async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      json: async () => ({ detail: 'Invalid API key' })
    }));

    render(ArtistImagesTab, baseProps());

    await waitFor(() => expect(screen.getByText(/Zoeken mislukt/)).toBeTruthy());
    expect(screen.getByText(/Invalid API key/)).toBeTruthy();
  });

  it('reports "no artists found" for an empty result', async () => {
    globalThis.fetch = mockSearch([], 0);

    render(ArtistImagesTab, baseProps());
    const input = screen.getByPlaceholderText('Zoek artiest...');
    await fireEvent.input(input, { target: { value: 'zzzz' } });

    await waitFor(() => expect(screen.getByText(/Geen artiesten gevonden/)).toBeTruthy(), { timeout: 2000 });
  });

  it('filters on artists without an image', async () => {
    render(ArtistImagesTab, baseProps());
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText('Zonder afbeelding'));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(String(globalThis.fetch.mock.calls[0][0])).toContain('only=without');
  });

  it('clears an image through the manager endpoint', async () => {
    const calls = [];
    globalThis.fetch = vi.fn(async (url, opts) => {
      calls.push({ url: String(url), method: opts?.method || 'GET' });
      return { ok: true, status: 200, json: async () => ({ items: [DAFT_PUNK], total: 1 }) };
    });

    render(ArtistImagesTab, baseProps());
    const button = await screen.findByTitle('Afbeelding verwijderen');
    await fireEvent.click(button);

    await waitFor(() => {
      expect(calls.some((c) => c.url.includes('/api/artists/28151/image/clear') && c.method === 'POST')).toBe(true);
    });
  });

  it('opens the artist detail with its stored images', async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (String(url).includes('/images')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            artist_id: 28151,
            artist_name: 'Daft Punk',
            primary_image_id: 11431,
            images: [
              { id: 11431, source: 'spotify', width: 640, height: 640, confidence: 95, is_primary: 1, exists_on_disk: true },
              { id: 999, source: 'lastfm', width: 300, height: 300, confidence: 60, is_primary: 0, exists_on_disk: true }
            ]
          })
        };
      }
      return { ok: true, status: 200, json: async () => ({ items: [DAFT_PUNK], total: 1 }) };
    });

    render(ArtistImagesTab, baseProps());
    const card = await screen.findByTitle('Beheer afbeeldingen van Daft Punk');
    await fireEvent.click(card);

    await waitFor(() => expect(screen.getByText('Opgeslagen afbeeldingen')).toBeTruthy());
    expect(screen.getByText('lastfm')).toBeTruthy();
  });
});
