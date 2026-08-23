import { render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ArtistView from '../../src/lib/ArtistView.svelte';
import GenreEdit from '../../src/lib/curation/GenreEdit.svelte';
import ArtistEdit from '../../src/lib/curation/ArtistEdit.svelte';
import {
  credentials,
  currentTrack,
  deduplicateEnabled,
  mumaUser,
  playerState,
  playlist,
  userPermissions,
  viewMode
} from '../../src/lib/store.js';

const ARTIST = { id: 'artist-1', name: 'Angerfist', album: [] };

function subsonicFetch(curationBody = {}) {
  return vi.fn(async (url) => {
    if (url.includes('/rest/getArtist?')) {
      return { ok: true, json: async () => ({ 'subsonic-response': { artist: ARTIST } }) };
    }
    if (url.includes('/api/curation/genres/')) {
      return { ok: true, json: async () => curationBody };
    }
    if (url.includes('/api/curation/artists/')) {
      return { ok: true, json: async () => curationBody };
    }
    if (url.includes('/api/rules/genres')) {
      return { ok: true, json: async () => [] };
    }
    return { ok: true, json: async () => ({ 'subsonic-response': { status: 'ok' } }) };
  });
}

beforeEach(() => {
  credentials.set({ url: '', username: 'user', password: 'pw' });
  viewMode.set('songs');
  deduplicateEnabled.set(false);
  playlist.set([]);
  currentTrack.set(null);
  playerState.set({ playing: false });
  userPermissions.set([]);
  mumaUser.set(null);
  globalThis.fetch = subsonicFetch();
});

afterEach(() => {
  vi.restoreAllMocks();
  userPermissions.set([]);
  mumaUser.set(null);
});

describe('the pencil on the artist page', () => {
  it('is not offered to a user who may not manage rules', async () => {
    render(ArtistView, { artistId: 'artist-1', onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText('Angerfist')).toBeTruthy());

    expect(screen.queryByLabelText('Artiest bewerken')).toBeNull();
  });

  it('is offered to a user who may', async () => {
    userPermissions.set(['rules.manage']);
    render(ArtistView, { artistId: 'artist-1', onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText('Angerfist')).toBeTruthy());

    expect(screen.getByLabelText('Artiest bewerken')).toBeTruthy();
  });

  it('navigates to the edit page for the artist being viewed', async () => {
    userPermissions.set(['rules.manage']);
    const onnavigate = vi.fn();
    render(ArtistView, { artistId: 'artist-1', onnavigate });
    await waitFor(() => expect(screen.getByText('Angerfist')).toBeTruthy());

    screen.getByLabelText('Artiest bewerken').click();

    expect(onnavigate).toHaveBeenCalledWith('artist-edit:artist-1');
  });
});

describe('the artist edit page', () => {
  it('trades the LMS id for the name MuMa knows, so a refresh still works', async () => {
    globalThis.fetch = subsonicFetch({
      name: 'Angerfist',
      artist_id: 7,
      mbid: null,
      in_library: true,
      external_ids: [],
      aliases: [],
      genre_rules: [],
      track_count: 143
    });

    render(ArtistEdit, { artistId: 'artist-1', onback: vi.fn() });

    await waitFor(() => expect(screen.getByText('143 tracks in de bibliotheek')).toBeTruthy());
    const called = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(called.some((url) => url.includes('/api/curation/artists/Angerfist'))).toBe(true);
  });
});

describe('the genre edit page', () => {
  const genre = (over = {}) => ({
    name: 'Industrial Hardcore',
    genre_id: 12,
    state: 'white',
    editable: true,
    occurrences: 40,
    parents: ['Hardcore'],
    children: [],
    ...over
  });

  it('shows the hierarchy of an accepted genre', async () => {
    globalThis.fetch = subsonicFetch(genre());
    render(GenreEdit, { name: 'Industrial Hardcore', onback: vi.fn() });

    await waitFor(() => expect(screen.getByText('Valt onder')).toBeTruthy());
    expect(screen.getByText('Hardcore')).toBeTruthy();
  });

  it('offers no form for a rejected genre, and says why', async () => {
    // Curation decides whether a genre exists; a rejected one is not in the library,
    // so a hierarchy for it would be a rule that can never fire.
    globalThis.fetch = subsonicFetch(genre({ state: 'black', editable: false }));
    render(GenreEdit, { name: 'Arts', onback: vi.fn() });

    await waitFor(() =>
      expect(screen.getByText('Dit genre is niet goedgekeurd door de curatie')).toBeTruthy());
    expect(screen.queryByText('Valt onder')).toBeNull();
  });
});
