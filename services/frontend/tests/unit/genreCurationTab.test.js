import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import GenreCurationTab from '../../src/lib/management/tabs/GenreCurationTab.svelte';

const UNKNOWN_ROW = { id: 1, name: 'Tribecore', state: 'unknown', occurrences: 12, canonical_targets: [] };
const WHITE_ROWS = [
  { id: 10, name: 'Hardcore', state: 'white' },
  { id: 11, name: 'Uptempo Hardcore', state: 'white' }
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

/** Answers the table request, the approved-genre request and any decision. */
function mockApi({ rows = [UNKNOWN_ROW], white = WHITE_ROWS, decisionOk = true, detail = 'Afgewezen' } = {}) {
  return vi.fn(async (url, options = {}) => {
    if (options.method === 'POST') return { ok: decisionOk, json: async () => ({ detail }) };
    if (url.includes('state=white&limit=1000')) return { ok: true, json: async () => white };
    return { ok: true, json: async () => rows };
  });
}

async function renderLoaded(overrides = {}) {
  const rendered = render(GenreCurationTab, props(overrides));
  await waitFor(() => expect(screen.getByText('Tribecore')).toBeTruthy());
  return rendered;
}

function decisions() {
  return globalThis.fetch.mock.calls.filter(([, options]) => options?.method === 'POST');
}

describe('GenreCurationTab', () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens on the genres still waiting for a decision', async () => {
    await renderLoaded();

    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes('state=unknown&limit=500'))).toBe(true);
    expect(screen.getByText('12')).toBeTruthy();
  });

  it('loads the approved genres separately as correction targets', async () => {
    await renderLoaded();

    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes('state=white&limit=1000'))).toBe(true);
  });

  it('switching the filter reloads the table for that state', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Afgekeurd'));

    await waitFor(() => {
      const urls = globalThis.fetch.mock.calls.map(([url]) => url);
      expect(urls.some((url) => url.includes('state=black&limit=500'))).toBe(true);
    });
  });

  it('the all filter asks for every state at once', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Alles'));

    await waitFor(() => {
      const urls = globalThis.fetch.mock.calls.map(([url]) => url);
      expect(urls.some((url) => url.endsWith('/api/rules/genres?limit=500'))).toBe(true);
    });
  });

  it('the search box narrows the table without another request', async () => {
    globalThis.fetch = mockApi({
      rows: [UNKNOWN_ROW, { id: 2, name: 'Speedcore', state: 'unknown', occurrences: 3 }]
    });
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.input(screen.getByPlaceholderText('Zoek genre...'), { target: { value: 'speed' } });

    expect(screen.queryByText('Tribecore')).toBeNull();
    expect(screen.getByText('Speedcore')).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it('reports a table that could not be loaded', async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
    const onError = vi.fn();

    render(GenreCurationTab, props({ onError }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Kon genres niet ophalen.'));
  });

  it('reports a table request that never arrived', async () => {
    globalThis.fetch = vi.fn(async () => { throw new Error('network down'); });
    const onError = vi.fn();

    render(GenreCurationTab, props({ onError }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Netwerkfout bij ophalen genres.'));
  });

  it('approving a genre straight from the table sends the decision', async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText('Goedkeuren'));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith('Tribecore goedgekeurd.'));
    const [url, options] = decisions()[0];
    expect(url).toBe('http://muma/api/rules/genres/1/decide');
    expect(JSON.parse(options.body).state).toBe('white');
  });

  it('rejecting a genre straight from the table sends the decision', async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText('Afkeuren'));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith('Tribecore afgekeurd.'));
    expect(JSON.parse(decisions()[0][1].body).state).toBe('black');
  });

  it('reports the reason a decision was refused', async () => {
    globalThis.fetch = mockApi({ decisionOk: false, detail: 'Genre is in gebruik' });
    const onError = vi.fn();
    await renderLoaded({ onError });

    await fireEvent.click(screen.getByText('Goedkeuren'));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Genre is in gebruik'));
  });

  it('correcting a genre offers the approved genres to map it onto', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Corrigeren'));

    expect(screen.getByText('Hardcore')).toBeTruthy();
    expect(screen.getByText('Uptempo Hardcore')).toBeTruthy();
  });

  it('a correction is saved with every target that was ticked', async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText('Corrigeren'));

    await fireEvent.click(screen.getAllByRole('checkbox')[1]);
    await fireEvent.click(screen.getByText('Opslaan'));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith('Tribecore wordt voortaan vervangen door Uptempo Hardcore.')
    );
    expect(JSON.parse(decisions()[0][1].body).canonical_ids).toEqual([11]);
  });

  it('a target can be unticked again', async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText('Corrigeren'));

    await fireEvent.click(screen.getAllByRole('checkbox')[0]);
    await fireEvent.click(screen.getAllByRole('checkbox')[0]);
    await fireEvent.click(screen.getByText('Opslaan'));

    await waitFor(() => expect(JSON.parse(decisions()[0][1].body).canonical_ids).toEqual([]));
  });

  it('a correction can map one genre onto several approved ones', async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText('Corrigeren'));

    await fireEvent.click(screen.getAllByRole('checkbox')[0]);
    await fireEvent.click(screen.getAllByRole('checkbox')[1]);
    await fireEvent.click(screen.getByText('Opslaan'));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        'Tribecore wordt voortaan vervangen door Hardcore + Uptempo Hardcore.'
      )
    );
  });

  it('an unknown genre is proposed for rejection by default', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Corrigeren'));
    await fireEvent.click(screen.getByText('Opslaan'));

    await waitFor(() => expect(JSON.parse(decisions()[0][1].body).state).toBe('black'));
  });

  it('the proposed state can be switched to approved', async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText('Corrigeren'));

    await fireEvent.click(screen.getAllByText('Goedkeuren')[1]);
    await fireEvent.click(screen.getByText('Opslaan'));

    await waitFor(() => expect(JSON.parse(decisions()[0][1].body).state).toBe('white'));
  });

  it('says so when there is nothing to correct onto', async () => {
    globalThis.fetch = mockApi({ white: [] });
    await renderLoaded();

    await fireEvent.click(screen.getByText('Corrigeren'));

    expect(screen.getByText('Nog geen goedgekeurde genres om naar te corrigeren.')).toBeTruthy();
  });

  it('cancelling closes the dialog without deciding anything', async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText('Corrigeren'));

    await fireEvent.click(screen.getByText('Annuleren'));

    expect(screen.queryByText('Opslaan')).toBeNull();
    expect(decisions()).toHaveLength(0);
  });
});
