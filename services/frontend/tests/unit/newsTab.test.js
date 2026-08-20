import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import NewsTab from '../../src/lib/management/tabs/NewsTab.svelte';

const SOURCE = {
  slug: 'nos',
  name: 'NOS Nieuws (NPO Radio 1)',
  stream_url: 'https://icecast.omroep.nl/radio1-bb-mp3',
  minute_of_hour: 0,
  duration_seconds: 600,
  retention_count: 12,
  enabled: true,
  last_error: null,
  last_success_at: 1787248800
};

const BULLETINS = [
  { id: 3, source: 'nos', started_at: 1787248800, duration_ms: 612000, size_bytes: 14688000 }
];

function props(overrides = {}) {
  return {
    API_BASE: 'http://muma',
    getHeaders: (extra = {}) => ({ 'x-api-key': 'key', ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    ...overrides
  };
}

function mockApi({ source = SOURCE, bulletins = BULLETINS, recordResult = { bulletin_id: 7 } } = {}) {
  return vi.fn(async (url, options = {}) => {
    if (url.includes('/record-now')) {
      return { ok: true, json: async () => recordResult };
    }
    if (options.method && options.method !== 'GET') {
      return { ok: true, json: async () => ({ slug: 'nos' }) };
    }
    if (url.includes('/api/news/bulletins')) {
      return { ok: true, json: async () => ({ bulletins }) };
    }
    return { ok: true, json: async () => ({ sources: [source] }) };
  });
}

function writes() {
  return globalThis.fetch.mock.calls.filter(([, options]) => options?.method && options.method !== 'GET');
}

describe('NewsTab', () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the configured source', async () => {
    render(NewsTab, props());
    await waitFor(() => expect(screen.getByDisplayValue('NOS Nieuws (NPO Radio 1)')).toBeTruthy());
    expect(screen.getByDisplayValue('https://icecast.omroep.nl/radio1-bb-mp3')).toBeTruthy();
    expect(screen.getByDisplayValue('600')).toBeTruthy();
  });

  it('lists the recordings that are still kept', async () => {
    render(NewsTab, props());
    await waitFor(() => expect(screen.getByText(/10:12/)).toBeTruthy());
  });

  it('saves the settings as a PUT on the source', async () => {
    render(NewsTab, props());
    await waitFor(() => expect(screen.getByDisplayValue('600')).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: /opslaan|save/i }));
    await waitFor(() => expect(writes().length).toBe(1));
    const [url, options] = writes()[0];
    expect(url).toBe('http://muma/api/news/sources/nos');
    expect(options.method).toBe('PUT');
    expect(JSON.parse(options.body).duration_seconds).toBe(600);
  });

  it('records on demand rather than waiting an hour', async () => {
    const onMessage = vi.fn();
    render(NewsTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByDisplayValue('600')).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: /nu opnemen|record now/i }));
    await waitFor(() => expect(onMessage).toHaveBeenCalled());
    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes('/record-now'))).toBe(true);
  });

  it('says so when a capture was discarded for being too short', async () => {
    globalThis.fetch = mockApi({ recordResult: { bulletin_id: null } });
    const onError = vi.fn();
    render(NewsTab, props({ onError }));
    await waitFor(() => expect(screen.getByDisplayValue('600')).toBeTruthy());
    await fireEvent.click(screen.getByRole('button', { name: /nu opnemen|record now/i }));
    await waitFor(() => expect(onError).toHaveBeenCalled());
  });
});
