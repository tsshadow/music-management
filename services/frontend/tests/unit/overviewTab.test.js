import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import OverviewTab from '../../src/lib/management/tabs/OverviewTab.svelte';

const CONTAINERS = [
  { name: 'music-manager', status: 'running' },
  { name: 'tagger', status: 'running' }
];

const STATS = {
  total_tracks: 12345,
  total_artists: 678,
  total_scrobbles: 90123,
  match_rate: 92,
  avg_track_duration: 245,
  total_unmatched: 42,
  top_genres: [
    { genre: 'Hardcore', count: 5000 },
    { genre: 'Uptempo', count: 1250 }
  ],
  recently_added: [
    { title: 'Raise Your Fist', artist: 'Angerfist', created_at: '2026-01-01T01:00:00Z' }
  ]
};

function props(overrides = {}) {
  return {
    containers: CONTAINERS,
    activity: {
      recent_added: [
        { title: 'Raise Your Fist', artist: 'Angerfist', timestamp: '2026-01-01T13:37:00Z' }
      ]
    },
    config: { version: '0.0.57' },
    allNotes: { 'music-manager': { version: '0.0.57', notes: '<p>Manager notes</p>' } },
    selectedServiceNotes: 'control-center',
    notes: { release_notes: '<p>Control centre notes</p>' },
    stats: STATS,
    fetchStats: vi.fn(),
    fetchArtistImages: vi.fn(),
    ...overrides
  };
}

describe('OverviewTab', () => {
  it('reports how many containers are running', () => {
    render(OverviewTab, props());

    expect(screen.getByText('2 / 2 Running')).toBeTruthy();
    expect(screen.getByText('Alle systemen werken naar behoren.')).toBeTruthy();
  });

  it('raises an alert naming the services that are down', () => {
    const containers = [
      { name: 'music-manager', status: 'running' },
      { name: 'tagger', status: 'exited' },
      { name: 'scanner', status: 'exited' }
    ];

    render(OverviewTab, props({ containers }));

    expect(screen.getByText('2 containers hebben problemen.')).toBeTruthy();
    expect(screen.getByText('tagger, scanner')).toBeTruthy();
  });

  it('shows the version that is running', () => {
    render(OverviewTab, props());

    expect(screen.getByText('0.0.57')).toBeTruthy();
  });

  it('shows a dash when there has been no activity at all', () => {
    render(OverviewTab, props({ activity: { recent_added: [] } }));

    expect(screen.getByText('-')).toBeTruthy();
    expect(screen.getByText('Geen recente activiteit gevonden.')).toBeTruthy();
  });

  it('falls back to the filename for a track without a title', () => {
    const activity = {
      recent_added: [{ file_path: '/music/unknown/track.mp3', source: 'soundcloud', timestamp: '2026-01-01T01:00:00Z' }]
    };

    render(OverviewTab, props({ activity }));

    expect(screen.getByText('track.mp3')).toBeTruthy();
    expect(screen.getByText('soundcloud')).toBeTruthy();
  });

  it('names a track it cannot identify at all', () => {
    const activity = { recent_added: [{ timestamp: '2026-01-01T01:00:00Z' }] };

    render(OverviewTab, props({ activity }));

    expect(screen.getByText('Onbekend')).toBeTruthy();
  });

  it('shows the collection figures with thousands separators', () => {
    render(OverviewTab, props());

    expect(screen.getByText('12.345')).toBeTruthy();
    expect(screen.getByText('678')).toBeTruthy();
    expect(screen.getByText('90.123')).toBeTruthy();
    expect(screen.getByText('92%')).toBeTruthy();
  });

  it('shows the average track length as minutes and seconds', () => {
    render(OverviewTab, props());

    expect(screen.getByText('4:05')).toBeTruthy();
  });

  it('lists the most popular genres', () => {
    render(OverviewTab, props());

    expect(screen.getByText('Hardcore')).toBeTruthy();
    expect(screen.getByText('5.000')).toBeTruthy();
  });

  it('scales each genre bar against the most popular one', () => {
    const { container } = render(OverviewTab, props());

    const [first, second] = [...container.querySelectorAll('.bg-spotify-green.h-1\\.5')];
    expect(first.getAttribute('style')).toContain('width: 100%');
    expect(second.getAttribute('style')).toContain('width: 25%');
  });

  it('says so when no genres are indexed yet', () => {
    render(OverviewTab, props({ stats: { ...STATS, top_genres: [] } }));

    expect(screen.getByText('Nog geen genres geïndexeerd. Draai een volledige scan.')).toBeTruthy();
  });

  it('lists what was recently added to the library', () => {
    render(OverviewTab, props());

    // Once in the activity list, once in the library table.
    expect(screen.getAllByText('Raise Your Fist')).toHaveLength(2);
    expect(screen.getAllByText('Angerfist')).toHaveLength(2);
  });

  it('shows the release notes of the control centre by default', () => {
    render(OverviewTab, props());

    expect(screen.getByText('Control centre notes')).toBeTruthy();
    expect(screen.getByText('Version 0.0.57')).toBeTruthy();
  });

  it('shows the release notes of another service when it is selected', () => {
    render(OverviewTab, props({ selectedServiceNotes: 'music-manager' }));

    expect(screen.getByText('Manager notes')).toBeTruthy();
  });

  it('refreshes the figures on request', async () => {
    const fetchStats = vi.fn();
    render(OverviewTab, props({ fetchStats }));

    await fireEvent.click(screen.getByText('VERNIEUWEN'));

    expect(fetchStats).toHaveBeenCalled();
  });

  it('starts an artist image fetch on request', async () => {
    const fetchArtistImages = vi.fn();
    render(OverviewTab, props({ fetchArtistImages }));

    await fireEvent.click(screen.getByText('IMAGES OPHALEN'));

    expect(fetchArtistImages).toHaveBeenCalled();
  });
});
