import { describe, it, expect } from 'vitest';
import {
  normalizeText,
  matchesSearch,
  queryCollection,
  defaultCollectionState,
  sortOption,
  thresholdMin,
  durationParts,
  COLLECTION_SORTS
} from '../../src/lib/collections';

const genre = (value, songCount = 100, albumCount = 10) => ({ value, songCount, albumCount });
const label = (value, songCount = 100, albumCount = 10) => ({ value, songCount, albumCount });
const playlist = (over = {}) => ({
  id: '1',
  name: 'Roadtrip',
  songCount: 20,
  duration: 3600,
  owner: 'user',
  public: false,
  created: '2026-01-01T00:00:00Z',
  changed: '2026-02-01T00:00:00Z',
  ...over
});

const names = (items) => items.map((i) => i.value ?? i.name);

describe('normalizeText', () => {
  it('strips accents and case so spelling variants match', () => {
    expect(normalizeText('Électro')).toBe('electro');
  });

  it('survives null and undefined without throwing', () => {
    expect(normalizeText(null)).toBe('');
    expect(normalizeText(undefined)).toBe('');
  });
});

describe('matchesSearch', () => {
  it('matches every term independently, so word order does not matter', () => {
    expect(matchesSearch('Drum & Bass', 'bass drum')).toBe(true);
  });

  it('rejects when one term is missing', () => {
    expect(matchesSearch('Drum & Bass', 'drum techno')).toBe(false);
  });

  it('treats an empty query as "everything"', () => {
    expect(matchesSearch('Hardstyle', '   ')).toBe(true);
  });
});

describe('queryCollection - genres', () => {
  const state = () => ({ ...defaultCollectionState('genres'), threshold: 'all' });

  it('sorts by name ascending by default', () => {
    const items = [genre('Techno'), genre('Ambient'), genre('Hardstyle')];
    expect(names(queryCollection(items, 'genres', state()))).toEqual(['Ambient', 'Hardstyle', 'Techno']);
  });

  it('sorts by song count descending when asked', () => {
    const items = [genre('Techno', 50), genre('Ambient', 900), genre('Hardstyle', 300)];
    const result = queryCollection(items, 'genres', { ...state(), sort: 'songs', direction: 'desc' });
    expect(names(result)).toEqual(['Ambient', 'Hardstyle', 'Techno']);
  });

  it('breaks count ties on name instead of leaving server order', () => {
    const items = [genre('Techno', 10), genre('Ambient', 10)];
    const result = queryCollection(items, 'genres', { ...state(), sort: 'songs', direction: 'desc' });
    expect(names(result)).toEqual(['Ambient', 'Techno']);
  });

  it('applies the minimum-songs threshold', () => {
    const items = [genre('Techno', 500), genre('Stray Tag', 3)];
    const result = queryCollection(items, 'genres', { ...state(), threshold: '10' });
    expect(names(result)).toEqual(['Techno']);
  });

  it('defaults to the 10+ threshold so the long tail stays hidden', () => {
    expect(defaultCollectionState('genres').threshold).toBe('10');
  });

  it('keeps only favorites when the favorites filter is on', () => {
    const items = [genre('Techno'), genre('Ambient')];
    const result = queryCollection(items, 'genres', { ...state(), favoritesOnly: true }, { favorites: ['Ambient'] });
    expect(names(result)).toEqual(['Ambient']);
  });

  it('does not mutate the array it was given', () => {
    const items = [genre('Techno'), genre('Ambient')];
    queryCollection(items, 'genres', { ...state(), sort: 'songs' });
    expect(names(items)).toEqual(['Techno', 'Ambient']);
  });
});

describe('queryCollection - labels', () => {
  it('filters on a search term and sorts by album count', () => {
    const items = [label('Hospital Records', 400, 40), label('Ram Records', 200, 90), label('Anjunabeats', 100, 5)];
    const result = queryCollection(
      items,
      'labels',
      { ...defaultCollectionState('labels'), search: 'records', sort: 'albums', direction: 'desc', threshold: 'all' }
    );
    expect(names(result)).toEqual(['Ram Records', 'Hospital Records']);
  });
});

describe('queryCollection - playlists', () => {
  const state = () => defaultCollectionState('playlists');

  it('ignores the size threshold, because a small playlist is still a playlist', () => {
    const items = [playlist({ id: '1', name: 'Kort', songCount: 2 })];
    expect(queryCollection(items, 'playlists', { ...state(), threshold: '100' })).toHaveLength(1);
  });

  it('sorts by last changed, newest first', () => {
    const items = [
      playlist({ id: '1', name: 'Oud', changed: '2025-01-01T00:00:00Z' }),
      playlist({ id: '2', name: 'Nieuw', changed: '2026-06-01T00:00:00Z' })
    ];
    const result = queryCollection(items, 'playlists', { ...state(), sort: 'changed', direction: 'desc' });
    expect(names(result)).toEqual(['Nieuw', 'Oud']);
  });

  it('keeps playlists without a date at the bottom rather than dropping them', () => {
    const items = [
      playlist({ id: '1', name: 'Geen datum', changed: undefined }),
      playlist({ id: '2', name: 'Met datum', changed: '2026-06-01T00:00:00Z' })
    ];
    const result = queryCollection(items, 'playlists', { ...state(), sort: 'changed', direction: 'desc' });
    expect(names(result)).toEqual(['Met datum', 'Geen datum']);
  });

  it('filters on public, accepting the string "true" the API sends', () => {
    const items = [
      playlist({ id: '1', name: 'Openbaar', public: 'true' }),
      playlist({ id: '2', name: 'Prive', public: false })
    ];
    expect(names(queryCollection(items, 'playlists', { ...state(), visibility: 'public' }))).toEqual(['Openbaar']);
    expect(names(queryCollection(items, 'playlists', { ...state(), visibility: 'private' }))).toEqual(['Prive']);
  });

  it('filters on owner for the "van mij" chip', () => {
    const items = [playlist({ id: '1', name: 'Mijn', owner: 'user' }), playlist({ id: '2', name: 'Andermans', owner: 'gast' })];
    const result = queryCollection(items, 'playlists', { ...state(), visibility: 'mine' }, { username: 'user' });
    expect(names(result)).toEqual(['Mijn']);
  });

  it('matches favorites on id, since playlist names are not unique', () => {
    const items = [playlist({ id: '1', name: 'Zelfde' }), playlist({ id: '2', name: 'Zelfde' })];
    const result = queryCollection(items, 'playlists', { ...state(), favoritesOnly: true }, { favorites: ['2'] });
    expect(result.map((p) => p.id)).toEqual(['2']);
  });
});

describe('sortOption', () => {
  it('falls back to the first option so a stale sort id cannot blank the view', () => {
    expect(sortOption('genres', 'nonsense').id).toBe('name');
  });

  it('offers a song-count sort for every collection', () => {
    for (const type of Object.keys(COLLECTION_SORTS)) {
      expect(COLLECTION_SORTS[type].some((s) => s.id === 'songs')).toBe(true);
    }
  });
});

describe('thresholdMin', () => {
  it('maps the chip id to a number and unknown ids to no filtering', () => {
    expect(thresholdMin('50')).toBe(50);
    expect(thresholdMin('all')).toBe(0);
    expect(thresholdMin('bogus')).toBe(0);
  });
});

describe('durationParts', () => {
  it('splits seconds into whole hours and the rest as minutes', () => {
    expect(durationParts(600)).toEqual({ hours: 0, minutes: 10 });
    expect(durationParts(3900)).toEqual({ hours: 1, minutes: 5 });
  });

  it('treats a missing or negative duration as zero', () => {
    expect(durationParts(undefined)).toEqual({ hours: 0, minutes: 0 });
    expect(durationParts(-60)).toEqual({ hours: 0, minutes: 0 });
  });
});
