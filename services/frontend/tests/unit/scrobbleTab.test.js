import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import ScrobbleTab from '../../src/lib/management/tabs/ScrobbleTab.svelte';

const IMPORTS = [
  {
    username: 'user', lb_username: 'someuser', status: 'completed',
    processed: 500, total_found: 1000, started_at: '2026-01-01T01:00:00Z'
  }
];

function props(overrides = {}) {
  return {
    API_BASE: 'http://muma',
    getHeaders: (extra = {}) => ({ 'x-api-key': 'key', ...extra }),
    users: [{ id: 1, username: 'user' }, { id: 2, username: 'guest' }],
    latestImports: IMPORTS,
    importMumaUser: '',
    importLbUser: '',
    isImporting: false,
    lbUsername: '',
    onMessage: vi.fn(),
    onError: vi.fn(),
    onSelectUser: vi.fn(),
    fetchLatestImports: vi.fn(),
    ...overrides
  };
}

function mockApi({ ok = true, lbUsername = 'someuser' } = {}) {
  return vi.fn(async () => ({ ok, json: async () => ({ lb_username: lbUsername }) }));
}

describe('ScrobbleTab', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('offers every user to import for', () => {
    render(ScrobbleTab, props());

    expect(screen.getByText('Kies gebruiker...')).toBeTruthy();
    const options = [...screen.getByLabelText('MuMa User').options].map((option) => option.value);
    expect(options).toEqual(['', 'user', 'guest']);
  });

  it('cannot start an import before a user is picked', () => {
    render(ScrobbleTab, props());

    expect(screen.getByText('IMPORT STARTEN').disabled).toBe(true);
  });

  it('starts the import for the selected user', async () => {
    const onMessage = vi.fn();
    render(ScrobbleTab, props({ importMumaUser: 'user', onMessage }));

    await fireEvent.click(screen.getByText('IMPORT STARTEN'));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith('ListenBrainz import gestart voor someuser!')
    );
    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe('http://muma/api/scrobble/import/listenbrainz');
    expect(JSON.parse(options.body)).toEqual({ username: 'user' });
  });

  it('an explicit ListenBrainz name is sent along', async () => {
    render(ScrobbleTab, props({ importMumaUser: 'user', importLbUser: 'someone-else' }));

    await fireEvent.click(screen.getByText('IMPORT STARTEN'));

    await waitFor(() =>
      expect(JSON.parse(globalThis.fetch.mock.calls[0][1].body)).toEqual({
        username: 'user', lb_username: 'someone-else'
      })
    );
  });

  it('falls back to the linked account in the message', async () => {
    globalThis.fetch = mockApi({ lbUsername: null });
    const onMessage = vi.fn();
    render(ScrobbleTab, props({ importMumaUser: 'user', onMessage }));

    await fireEvent.click(screen.getByText('IMPORT STARTEN'));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith('ListenBrainz import gestart voor gekoppeld account!')
    );
  });

  it('reloads the import history right after starting', async () => {
    const fetchLatestImports = vi.fn();
    render(ScrobbleTab, props({ importMumaUser: 'user', fetchLatestImports }));

    await fireEvent.click(screen.getByText('IMPORT STARTEN'));

    await waitFor(() => expect(fetchLatestImports).toHaveBeenCalled());
  });

  it('keeps polling the history while an import is running', async () => {
    const fetchLatestImports = vi.fn();
    const running = [{ ...IMPORTS[0], status: 'running' }];
    render(ScrobbleTab, props({ importMumaUser: 'user', latestImports: running, fetchLatestImports }));
    await fireEvent.click(screen.getByText('IMPORT STARTEN'));
    await waitFor(() => expect(fetchLatestImports).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(3000);
    await vi.advanceTimersByTimeAsync(3000);

    expect(fetchLatestImports.mock.calls.length).toBeGreaterThan(2);
  });

  it('stops polling once nothing is running any more', async () => {
    const fetchLatestImports = vi.fn();
    render(ScrobbleTab, props({ importMumaUser: 'user', fetchLatestImports }));
    await fireEvent.click(screen.getByText('IMPORT STARTEN'));
    await waitFor(() => expect(fetchLatestImports).toHaveBeenCalledTimes(1));

    await vi.advanceTimersByTimeAsync(3000);
    const afterFirstPoll = fetchLatestImports.mock.calls.length;
    await vi.advanceTimersByTimeAsync(9000);

    expect(fetchLatestImports.mock.calls.length).toBe(afterFirstPoll);
  });

  it('reports a server that refused the import', async () => {
    globalThis.fetch = mockApi({ ok: false });
    const onError = vi.fn();
    render(ScrobbleTab, props({ importMumaUser: 'user', onError }));

    await fireEvent.click(screen.getByText('IMPORT STARTEN'));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Kon import niet starten.'));
  });

  it('reports an import request that never arrived', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });
    const onError = vi.fn();
    render(ScrobbleTab, props({ importMumaUser: 'user', onError }));

    await fireEvent.click(screen.getByText('IMPORT STARTEN'));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Netwerkfout bij starten import.'));
  });

  it('picking a user asks the parent to load their linked account', async () => {
    const onSelectUser = vi.fn();
    render(ScrobbleTab, props({ onSelectUser }));

    const select = screen.getByLabelText('MuMa User');
    await fireEvent.change(select, { target: { value: 'user' } });

    expect(onSelectUser).toHaveBeenCalledWith({ id: 1, username: 'user' });
  });

  it('shows that an account is already linked', () => {
    render(ScrobbleTab, props({ lbUsername: 'someuser' }));

    expect(screen.getByText('GEKOPPELD')).toBeTruthy();
    expect(screen.getByPlaceholderText('Gekoppeld: someuser')).toBeTruthy();
  });

  it('hides the linked marker once a name is typed', () => {
    render(ScrobbleTab, props({ lbUsername: 'someuser', importLbUser: 'other' }));

    expect(screen.queryByText('GEKOPPELD')).toBeNull();
  });

  it('lists the recent imports with their progress', () => {
    const { container } = render(ScrobbleTab, props());

    expect(screen.getByText('LB: someuser')).toBeTruthy();
    expect(screen.getByText('500 / 1000')).toBeTruthy();
    expect(container.querySelector('.bg-brand.h-1\\.5').getAttribute('style')).toContain('width: 50%');
  });

  it('an import that found nothing shows an empty bar', () => {
    const imports = [{ ...IMPORTS[0], processed: 0, total_found: 0 }];
    const { container } = render(ScrobbleTab, props({ latestImports: imports }));

    expect(container.querySelector('.bg-brand.h-1\\.5').getAttribute('style')).toContain('width: 0%');
  });

  it('says so when nothing has been imported yet', () => {
    render(ScrobbleTab, props({ latestImports: [] }));

    expect(screen.getByText('Geen import geschiedenis gevonden.')).toBeTruthy();
  });

  it('shows the import as busy while it runs', () => {
    render(ScrobbleTab, props({ importMumaUser: 'user', isImporting: true }));

    expect(screen.getByText('IMPORT BEZIG...').disabled).toBe(true);
  });

  it('reloads the history on request', async () => {
    const fetchLatestImports = vi.fn();
    const { container } = render(ScrobbleTab, props({ fetchLatestImports }));

    await fireEvent.click(container.querySelector('h3 button'));

    expect(fetchLatestImports).toHaveBeenCalled();
  });
});
