import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import TrackTable from '../../src/lib/management/library/TrackTable.svelte';

const noop = () => {};

const base = {
  tracks: [],
  total: 0,
  page: 1,
  limit: 100,
  loading: false,
  error: null,
  selectedTrack: null,
  onSelect: noop,
  onPage: noop,
};

describe('TrackTable', () => {
  it('shows the server failure instead of an empty result', () => {
    // The whole point of the fix: /api/library/advanced returned 500 for every
    // request and the old page rendered that as "no tracks found".
    render(TrackTable, {
      ...base,
      error: "Serverfout 500 bij /api/library/advanced. Unknown column 'af.musical_key'",
    });
    expect(screen.getByText('Laden mislukt')).toBeTruthy();
    expect(screen.getByText(/Unknown column/)).toBeTruthy();
    expect(screen.queryByText(/Geen tracks gevonden/)).toBeNull();
  });

  it('shows the empty-result message only when the server really returned nothing', () => {
    render(TrackTable, { ...base, tracks: [], total: 0 });
    expect(screen.getByText(/Geen tracks gevonden/)).toBeTruthy();
    expect(screen.queryByText('Laden mislukt')).toBeNull();
  });

  it('renders duration, bpm, year and genres for a track', () => {
    render(TrackTable, {
      ...base,
      total: 1,
      tracks: [{
        id: 1,
        title: 'Test Track',
        artist: 'Angerfist',
        label: 'Footworxx',
        genres: ['Hardcore', 'Uptempo Hardcore'],
        bpm: 190.4,
        release_year: 2024,
        duration_secs: 312,
      }],
    });
    expect(screen.getByText('Test Track')).toBeTruthy();
    expect(screen.getByText('190')).toBeTruthy();
    expect(screen.getByText('2024')).toBeTruthy();
    // 312 seconds, the column that always showed '-' because the query never
    // selected duration_secs.
    expect(screen.getByText('5:12')).toBeTruthy();
    expect(screen.getByText('Hardcore')).toBeTruthy();
    expect(screen.getByText('Uptempo Hardcore')).toBeTruthy();
  });

  it('falls back to a dash for fields the library does not hold', () => {
    render(TrackTable, {
      ...base,
      total: 1,
      tracks: [{
        id: 2, title: 'Bare', artist: null, label: null,
        genres: [], bpm: null, release_year: null, duration_secs: null,
      }],
    });
    expect(screen.getAllByText('-').length).toBe(5);
  });

  it('hides pagination when everything fits on one page', () => {
    render(TrackTable, { ...base, total: 10, limit: 100 });
    expect(screen.queryByText('1 / 1')).toBeNull();
  });
});
