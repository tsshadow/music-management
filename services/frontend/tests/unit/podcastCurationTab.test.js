import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import PodcastCurationTab from '../../src/lib/management/tabs/PodcastCurationTab.svelte';

const UNKNOWN_ROW = {
  id: 1,
  name: 'DJ ISAAC - HARDSTYLE SESSIONS',
  state: 'unknown',
  occurrences: 131,
  aliases: ['DJ ISAAC - HARDSTYLE SESSIONS', 'Hardstyle Sessions']
};
const WHITE_ROWS = [
  { id: 10, name: "Isaac's Hardstyle Sessions", state: 'white', aliases: [] },
  { id: 11, name: 'Hard With Style', state: 'white', aliases: [] }
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

/** Answers the table request, the approved-show request and any decision. */
function mockApi({ rows = [UNKNOWN_ROW], white = WHITE_ROWS, decisionOk = true, detail = 'Afgewezen' } = {}) {
  return vi.fn(async (url, options = {}) => {
    if (options.method === 'POST') return { ok: decisionOk, json: async () => ({ detail }) };
    if (url.includes('state=white&limit=1000')) return { ok: true, json: async () => white };
    return { ok: true, json: async () => rows };
  });
}

async function renderLoaded(overrides = {}) {
  const rendered = render(PodcastCurationTab, props(overrides));
  await waitFor(() => expect(screen.getByText('DJ ISAAC - HARDSTYLE SESSIONS')).toBeTruthy());
  return rendered;
}

function decisions() {
  return globalThis.fetch.mock.calls.filter(([, options]) => options?.method === 'POST');
}

describe('PodcastCurationTab', () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('opens on the shows still waiting for a decision', async () => {
    await renderLoaded();

    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes('state=unknown&limit=500'))).toBe(true);
  });

  it('shows how many episodes a decision covers', async () => {
    await renderLoaded();

    expect(screen.getByText('131 afleveringen')).toBeTruthy();
  });

  it('lists the other spellings under the name', async () => {
    await renderLoaded();

    expect(screen.getByText('Ook geschreven als Hardstyle Sessions')).toBeTruthy();
  });

  it('leaves out a spelling that only differs in casing from the name', async () => {
    await renderLoaded();

    expect(screen.queryByText(/DJ ISAAC - HARDSTYLE SESSIONS ·/)).toBeNull();
  });

  it('loads the approved shows separately as merge targets', async () => {
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

  it('approving a show posts white for it', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Goedkeuren'));

    await waitFor(() => expect(decisions()).toHaveLength(1));
    const [url, options] = decisions()[0];
    expect(url).toBe('http://muma/api/rules/podcasts/1/decide');
    expect(JSON.parse(options.body)).toEqual({ state: 'white', host: null, station: null });
  });

  it('rejecting a show posts black for it', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Afkeuren'));

    await waitFor(() => expect(decisions()).toHaveLength(1));
    expect(JSON.parse(decisions()[0][1].body).state).toBe('black');
  });

  it('merging posts the target instead of a state change', async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText('Samenvoegen'));
    const select = await screen.findByLabelText('Samenvoegen met (optioneel)');
    await fireEvent.change(select, { target: { value: '10' } });
    await fireEvent.click(screen.getByText('Opslaan'));

    await waitFor(() => expect(decisions()).toHaveLength(1));
    expect(JSON.parse(decisions()[0][1].body)).toEqual({ state: 'white', merge_into_podcast_id: 10 });
  });

  it('the merge dialog does not offer the row itself', async () => {
    await renderLoaded({ });

    await fireEvent.click(screen.getByText('Samenvoegen'));
    const select = await screen.findByLabelText('Samenvoegen met (optioneel)');
    const options = [...select.querySelectorAll('option')].map((option) => option.textContent);

    expect(options).not.toContain('DJ ISAAC - HARDSTYLE SESSIONS');
    expect(options).toContain("Isaac's Hardstyle Sessions");
  });

  it('reports the server error when a decision fails', async () => {
    const onError = vi.fn();
    globalThis.fetch = mockApi({ decisionOk: false, detail: 'Unknown podcast' });
    await renderLoaded({ onError });

    await fireEvent.click(screen.getByText('Goedkeuren'));

    await waitFor(() => expect(onError).toHaveBeenCalledWith('Unknown podcast'));
  });

  it('says the queue is empty rather than showing an empty table', async () => {
    globalThis.fetch = mockApi({ rows: [] });
    render(PodcastCurationTab, props());

    await waitFor(() =>
      expect(screen.getByText('Niets te beoordelen. Alle shows hebben een beslissing.')).toBeTruthy()
    );
  });
});
