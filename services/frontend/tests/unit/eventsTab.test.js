import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import { get } from 'svelte/store';
import EventsTab from '../../src/lib/management/tabs/EventsTab.svelte';
import { t } from '../../src/lib/i18n/index.js';

// Resolved through the translator rather than hardcoded, so re-wording a string
// is a copy change and not a test failure.
const text = (key) => get(t)(key);

const EVENTS = [
  {
    id: 1,
    level: 'ERROR',
    source: 'downloader',
    title: 'SoundCloud rejected the token',
    message: 'HTTP 401 on /resolve',
    created_at: '2026-01-01T01:00:00Z'
  },
  {
    id: 2,
    level: 'INFO',
    source: 'music-manager',
    title: 'Tagger finished',
    message: '3 tracks tagged',
    created_at: '2026-01-02T01:00:00Z'
  }
];

function props(overrides = {}) {
  return {
    API_BASE: 'http://muma',
    getHeaders: () => ({ 'x-api-key': 'key' }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    config: {},
    ...overrides
  };
}

/** A fetch that answers the initial load, then whatever the mutations get. */
function mockApi(events = EVENTS, { mutationOk = true } = {}) {
  return vi.fn(async (_url, options = {}) => {
    if (!options.method) {
      return {
        ok: true,
        json: async () => ({
          events,
          counts: { INFO: 1, WARNING: 0, ERROR: 1, CRITICAL: 0 },
          total: events.length
        })
      };
    }
    return { ok: mutationOk };
  });
}

async function renderLoaded(overrides = {}) {
  const rendered = render(EventsTab, props(overrides));
  await waitFor(() => expect(screen.getByText('SoundCloud rejected the token')).toBeTruthy());
  return rendered;
}

describe('EventsTab', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    globalThis.fetch = mockApi();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('lists the entries it loaded, with every level selected up front', async () => {
    await renderLoaded();

    expect(screen.getByText('Tagger finished')).toBeTruthy();
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toContain('http://muma/api/events?');
    expect(url).toContain('level=INFO');
    expect(url).toContain('level=CRITICAL');
    expect(options).toEqual({ headers: { 'x-api-key': 'key' } });
  });

  it('says so when nothing matches the filters', async () => {
    globalThis.fetch = mockApi([]);

    render(EventsTab, props());

    await waitFor(() => expect(screen.getByText(text('management.events.empty'))).toBeTruthy());
  });

  it('shows nothing rather than crashing on a 200 with an unexpected body', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));

    render(EventsTab, props());

    await waitFor(() => expect(screen.getByText(text('management.events.empty'))).toBeTruthy());
  });

  it('reports a failed load rather than rendering an empty list silently', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });
    const onError = vi.fn();

    render(EventsTab, props({ onError }));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(text('management.events.fetchFailed'))
    );
  });

  it('shows both ntfy topics from the configuration', async () => {
    await renderLoaded({
      config: {
        notify_url: 'https://ntfy.example/',
        notify_topic: 'muma-prod',
        notify_topic_alerts: 'muma-prod-alerts'
      }
    });

    expect(screen.getByText('https://ntfy.example/muma-prod')).toBeTruthy();
    expect(screen.getByText('https://ntfy.example/muma-prod-alerts')).toBeTruthy();
  });

  it('falls back to the default topic names', async () => {
    await renderLoaded();

    expect(screen.getByText('music-management')).toBeTruthy();
    expect(screen.getByText('music-management-alerts')).toBeTruthy();
  });

  it('keeps the counts visible for a level that is switched off', async () => {
    await renderLoaded();

    // The badge is the whole point of the level chips: it is how you see what is
    // hiding behind a filter you turned off.
    await fireEvent.click(screen.getByText('INFO 1'));

    await waitFor(() => expect(screen.getByText('INFO 1')).toBeTruthy());
  });

  it('asks the server again with only the levels still selected', async () => {
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText('INFO 1'));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).not.toContain('level=INFO');
    expect(url).toContain('level=ERROR');
  });

  it('shows the message only once an entry is expanded', async () => {
    await renderLoaded();

    expect(screen.queryByText('HTTP 401 on /resolve')).toBeNull();

    await fireEvent.click(screen.getByText('SoundCloud rejected the token'));

    await waitFor(() => expect(screen.getByText('HTTP 401 on /resolve')).toBeTruthy());
  });

  it('removes a single entry from the list once the server confirms', async () => {
    const { container } = await renderLoaded();

    await fireEvent.click(container.querySelectorAll('.group button')[1]);

    await waitFor(() =>
      expect(screen.queryByText('SoundCloud rejected the token')).toBeNull()
    );
    expect(screen.getByText('Tagger finished')).toBeTruthy();
    expect(globalThis.fetch).toHaveBeenCalledWith('http://muma/api/events/1', {
      method: 'DELETE',
      headers: { 'x-api-key': 'key' }
    });
  });

  it('keeps an entry the server refused to delete', async () => {
    globalThis.fetch = mockApi(EVENTS, { mutationOk: false });
    const { container } = await renderLoaded();

    await fireEvent.click(container.querySelectorAll('.group button')[1]);

    await waitFor(() =>
      expect(screen.getByText('SoundCloud rejected the token')).toBeTruthy()
    );
  });

  it('clears every entry after the confirmation', async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText(text('management.events.clearAll')));

    await waitFor(() => expect(screen.getByText(text('management.events.empty'))).toBeTruthy());
    expect(onMessage).toHaveBeenCalledWith(text('management.events.cleared'));
  });

  it('clears nothing when the confirmation is declined', async () => {
    window.confirm.mockReturnValue(false);
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText(text('management.events.clearAll')));

    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(screen.getByText('SoundCloud rejected the token')).toBeTruthy();
  });

  it('reports a clear that never reached the server', async () => {
    const onError = vi.fn();
    await renderLoaded({ onError });
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    await fireEvent.click(screen.getByText(text('management.events.clearAll')));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(text('management.events.clearFailed'))
    );
  });

  it('offers nothing to clear when the list is empty', async () => {
    globalThis.fetch = mockApi([]);

    render(EventsTab, props());

    await waitFor(() => expect(screen.getByText(text('management.events.empty'))).toBeTruthy());
    expect(screen.queryByText(text('management.events.clearAll'))).toBeNull();
  });

  it('reloads the list on request', async () => {
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText(text('management.events.refresh')));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1));
  });

  it('stops polling once the tab is gone', async () => {
    const { unmount } = await renderLoaded();
    unmount();
    globalThis.fetch.mockClear();

    await vi.advanceTimersByTimeAsync(30000);

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
