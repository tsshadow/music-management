import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import HealthTab from '../../src/lib/management/tabs/HealthTab.svelte';

const CONTAINERS = [
  { name: 'music-manager', image: 'muma/music-manager:0.0.56', status: 'running' },
  { name: 'tagger', image: 'muma/tagger:0.0.56', status: 'exited' }
];

const ACTIVITY = {
  recent_added: [
    { file_path: '/music/angerfist/raise-your-fist.mp3', title: 'Raise Your Fist', artist: 'Angerfist', timestamp: '2026-01-01T01:00:00Z' },
    { file_path: '/music/unknown/track.mp3', source: 'soundcloud', timestamp: '2026-01-01T02:00:00Z' }
  ],
  recent_tagged: [
    { file_path: '/music/outsiders/thunder.mp3', title: 'Thunder', artist: 'Outsiders', timestamp: '2026-01-01T03:00:00Z' }
  ]
};

function props(overrides = {}) {
  return {
    containers: CONTAINERS,
    activity: ACTIVITY,
    API_BASE: 'http://muma',
    getHeaders: () => ({ 'x-api-key': 'key' }),
    refreshSystemStatus: vi.fn(),
    ...overrides
  };
}

function mockLogsApi(response) {
  return vi.fn(async () => response);
}

describe('HealthTab', () => {
  beforeEach(() => {
    globalThis.fetch = mockLogsApi({ ok: true, json: async () => ({ logs: 'started ok' }) });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists every container with its image and status', () => {
    render(HealthTab, props());

    expect(screen.getByText('music-manager')).toBeTruthy();
    expect(screen.getByText('muma/music-manager:0.0.56')).toBeTruthy();
    expect(screen.getByText('running')).toBeTruthy();
    expect(screen.getByText('exited')).toBeTruthy();
  });

  it('falls back to the filename and source for a track without tags', () => {
    render(HealthTab, props());

    expect(screen.getByText('Raise Your Fist')).toBeTruthy();
    expect(screen.getByText('track.mp3')).toBeTruthy();
    expect(screen.getByText('soundcloud')).toBeTruthy();
  });

  it('shows recently tagged tracks separately from recently added ones', () => {
    render(HealthTab, props());

    expect(screen.getByText('Recent Toegevoegd')).toBeTruthy();
    expect(screen.getByText('Recent Getagged')).toBeTruthy();
    expect(screen.getByText('Thunder')).toBeTruthy();
  });

  it('hides the log viewer until a container is picked', () => {
    render(HealthTab, props());

    expect(screen.queryByText(/^Logs: /)).toBeNull();
  });

  it('loads the logs of the container whose button was pressed', async () => {
    const { container } = render(HealthTab, props());

    await fireEvent.click(container.querySelectorAll('tbody button')[0]);

    await waitFor(() => expect(screen.getByText(/started ok/)).toBeTruthy());
    expect(globalThis.fetch).toHaveBeenCalledWith(
      'http://muma/api/system/logs/music-manager?tail=200',
      { headers: { 'x-api-key': 'key' } }
    );
    expect(screen.getByText('Logs: music-manager')).toBeTruthy();
  });

  it('reports a rejected log request instead of showing nothing', async () => {
    globalThis.fetch = mockLogsApi({ ok: false });
    const { container } = render(HealthTab, props());

    await fireEvent.click(container.querySelectorAll('tbody button')[0]);

    await waitFor(() => expect(screen.getByText(/Kon logs niet ophalen\./)).toBeTruthy());
  });

  it('reports a failed log request instead of showing nothing', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });
    const { container } = render(HealthTab, props());

    await fireEvent.click(container.querySelectorAll('tbody button')[0]);

    await waitFor(() => expect(screen.getByText(/Fout bij ophalen logs\./)).toBeTruthy());
  });

  it('can close the log viewer again', async () => {
    const { container } = render(HealthTab, props());
    await fireEvent.click(container.querySelectorAll('tbody button')[0]);
    await waitFor(() => expect(screen.getByText('Logs: music-manager')).toBeTruthy());

    await fireEvent.click(screen.getByText('×'));

    expect(screen.queryByText('Logs: music-manager')).toBeNull();
  });

  it('reloads the logs of the container already on screen', async () => {
    const { container } = render(HealthTab, props());
    await fireEvent.click(container.querySelectorAll('tbody button')[0]);
    await waitFor(() => expect(screen.getByText('Logs: music-manager')).toBeTruthy());

    const [reload] = screen.getAllByRole('button').slice(-2);
    await fireEvent.click(reload);

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));
  });

  it('refreshes the whole system status on request', async () => {
    const refreshSystemStatus = vi.fn();
    render(HealthTab, props({ refreshSystemStatus }));

    await fireEvent.click(screen.getByText('Vernieuwen'));

    expect(refreshSystemStatus).toHaveBeenCalled();
  });
});
