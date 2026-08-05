import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/svelte';
import AboutTab from '../../src/lib/management/tabs/AboutTab.svelte';
import WorkerVersionsTab from '../../src/lib/management/tabs/WorkerVersionsTab.svelte';

describe('AboutTab', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, text: async () => '<p>Over MuMa</p>' }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the page the server returns', async () => {
    render(AboutTab, { apiKey: 'key', API_BASE: 'http://muma' });

    await waitFor(() => expect(screen.getByText('Over MuMa')).toBeTruthy());
    expect(globalThis.fetch).toHaveBeenCalledWith('http://muma/api/about', {
      headers: { 'X-API-Key': 'key' }
    });
  });

  it('reports a server that refused the page', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, statusText: 'Forbidden', text: async () => '' }));

    render(AboutTab, { apiKey: 'key', API_BASE: 'http://muma' });

    await waitFor(() => expect(screen.getByText(/Forbidden/)).toBeTruthy());
  });

  it('reports a page that never arrived', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    render(AboutTab, { apiKey: 'key', API_BASE: 'http://muma' });

    await waitFor(() => expect(screen.getByText(/network down/)).toBeTruthy());
  });
});

describe('WorkerVersionsTab', () => {
  it('lists the version of every worker', () => {
    render(WorkerVersionsTab, { versions: { tagger: '0.0.57', scanner: '0.0.57' } });

    expect(screen.getByText('tagger')).toBeTruthy();
    expect(screen.getAllByText('0.0.57').length).toBeGreaterThan(0);
  });

  it('marks a worker that is offline', () => {
    render(WorkerVersionsTab, { versions: { tagger: 'offline' } });

    expect(screen.getByText('offline').className).toContain('text-red-500');
  });

  it('marks a worker that answered', () => {
    render(WorkerVersionsTab, { versions: { tagger: '0.0.57' } });

    expect(screen.getAllByText('0.0.57')[0].className).toContain('text-spotify-green');
  });

  it('shows the external references it could resolve', () => {
    render(WorkerVersionsTab, { versions: { lms: '0.7.1', ultrasonic: '6.9.2' } });

    // Once in the per-worker grid, once in the external references block.
    expect(screen.getAllByText('0.7.1')).toHaveLength(2);
    expect(screen.getAllByText('6.9.2')).toHaveLength(2);
  });

  it('says so when an external reference is missing', () => {
    render(WorkerVersionsTab, { versions: {} });

    expect(screen.getByText('Niet gedetecteerd')).toBeTruthy();
    expect(screen.getByText('Niet gevonden')).toBeTruthy();
  });
});
