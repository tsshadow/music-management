import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import NotificationsTab from '../../src/lib/management/tabs/NotificationsTab.svelte';

const NOTIFICATIONS = [
  { id: 1, title: 'SoundCloud', message: '12 tracks gedownload', created_at: '2026-01-01T01:00:00Z' },
  { id: 2, title: 'Tagger', message: '3 tracks getagged', created_at: '2026-01-02T01:00:00Z' }
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
function mockApi(notifications = NOTIFICATIONS, { mutationOk = true } = {}) {
  return vi.fn(async (_url, options = {}) => {
    if (!options.method) return { ok: true, json: async () => notifications };
    return { ok: mutationOk };
  });
}

async function renderLoaded(overrides = {}) {
  const rendered = render(NotificationsTab, props(overrides));
  await waitFor(() => expect(screen.getByText('SoundCloud')).toBeTruthy());
  return rendered;
}

describe('NotificationsTab', () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists the notifications it loaded', async () => {
    await renderLoaded();

    expect(screen.getByText('12 tracks gedownload')).toBeTruthy();
    expect(screen.getByText('3 tracks getagged')).toBeTruthy();
    expect(globalThis.fetch).toHaveBeenCalledWith('http://muma/api/notifications', {
      headers: { 'x-api-key': 'key' }
    });
  });

  it('says so when there is nothing to show', async () => {
    globalThis.fetch = mockApi([]);

    render(NotificationsTab, props());

    await waitFor(() => expect(screen.getByText('Geen nieuwe meldingen.')).toBeTruthy());
  });

  it('reports a failed load rather than rendering an empty list silently', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });
    const onError = vi.fn();

    render(NotificationsTab, props({ onError }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Kon meldingen niet ophalen.'));
  });

  it('shows the ntfy subscription address from the configuration', async () => {
    await renderLoaded({ config: { notify_url: 'https://ntfy.example/', notify_topic: 'muma-prod' } });

    expect(screen.getByText('https://ntfy.example/muma-prod')).toBeTruthy();
  });

  it('falls back to the default ntfy address', async () => {
    await renderLoaded();

    expect(screen.getByText('https://ntfy.example.com/music-management')).toBeTruthy();
  });

  it('removes a single notification from the list once the server confirms', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getAllByTitle('Verwijderen')[0]);

    await waitFor(() => expect(screen.queryByText('SoundCloud')).toBeNull());
    expect(screen.getByText('Tagger')).toBeTruthy();
    expect(globalThis.fetch).toHaveBeenCalledWith('http://muma/api/notifications/1', {
      method: 'DELETE',
      headers: { 'x-api-key': 'key' }
    });
  });

  it('keeps a notification the server refused to delete', async () => {
    globalThis.fetch = mockApi(NOTIFICATIONS, { mutationOk: false });
    await renderLoaded();

    await fireEvent.click(screen.getAllByTitle('Verwijderen')[0]);

    await waitFor(() => expect(screen.getByText('SoundCloud')).toBeTruthy());
  });

  it('reports a delete that never reached the server', async () => {
    const onError = vi.fn();
    await renderLoaded({ onError });
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    await fireEvent.click(screen.getAllByTitle('Verwijderen')[0]);

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Kon melding niet verwijderen.'));
  });

  it('clears every notification after the confirmation', async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText('Alles wissen'));

    await waitFor(() => expect(screen.getByText('Geen nieuwe meldingen.')).toBeTruthy());
    expect(onMessage).toHaveBeenCalledWith('Alle meldingen gewist.');
  });

  it('clears nothing when the confirmation is declined', async () => {
    window.confirm.mockReturnValue(false);
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText('Alles wissen'));

    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(screen.getByText('SoundCloud')).toBeTruthy();
  });

  it('reports a clear that never reached the server', async () => {
    const onError = vi.fn();
    await renderLoaded({ onError });
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });

    await fireEvent.click(screen.getByText('Alles wissen'));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Kon meldingen niet wissen.'));
  });

  it('offers nothing to clear when the list is empty', async () => {
    globalThis.fetch = mockApi([]);

    render(NotificationsTab, props());

    await waitFor(() => expect(screen.getByText('Geen nieuwe meldingen.')).toBeTruthy());
    expect(screen.queryByText('Alles wissen')).toBeNull();
  });

  it('reloads the list on request', async () => {
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText('Vernieuwen'));

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1));
  });
});
