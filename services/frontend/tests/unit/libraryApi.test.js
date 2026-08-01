import { describe, it, expect, vi, afterEach } from 'vitest';
import { buildQuery, apiGet, emptyFilters } from '../../src/lib/management/library/api.js';

const headers = () => ({ 'x-api-key': 'k' });

afterEach(() => { vi.restoreAllMocks(); });

describe('buildQuery', () => {
  it('omits empty values', () => {
    expect(buildQuery(emptyFilters())).toBe('');
  });

  it('repeats a parameter for each selected value', () => {
    const q = buildQuery({ ...emptyFilters(), genre: ['Hardcore', 'Frenchcore'] });
    expect(q).toBe('genre=Hardcore&genre=Frenchcore');
  });

  it('encodes values with spaces and ampersands', () => {
    const q = buildQuery({ ...emptyFilters(), artist: ['Sub Zero Project', 'D&B'] });
    expect(q).toBe('artist=Sub+Zero+Project&artist=D%26B');
  });

  it('includes numeric bounds but not nulls', () => {
    const q = buildQuery({ ...emptyFilters(), bpm_min: 140, bpm_max: null });
    expect(q).toBe('bpm_min=140');
  });

  it('includes analyzed when false', () => {
    const q = buildQuery({ ...emptyFilters(), analyzed: false });
    expect(q).toBe('analyzed=false');
  });

  it('includes free text', () => {
    expect(buildQuery({ ...emptyFilters(), q: 'angerfist' })).toBe('q=angerfist');
  });

  it('drops empty strings inside a list', () => {
    expect(buildQuery({ ...emptyFilters(), genre: ['', 'Terror'] })).toBe('genre=Terror');
  });
});

describe('apiGet', () => {
  it('returns the parsed body on success', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({ tracks: [] }),
    });
    await expect(apiGet('http://x', '/api/library/advanced', emptyFilters(), headers))
      .resolves.toEqual({ tracks: [] });
  });

  it('throws with the status on a non-ok response instead of returning empty', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false, status: 500, text: async () => 'Unknown column',
    });
    await expect(apiGet('http://x', '/api/library/advanced', emptyFilters(), headers))
      .rejects.toThrow(/500/);
  });

  it('throws a readable message on a network failure', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('failed to fetch'));
    await expect(apiGet('http://x', '/api/library/advanced', emptyFilters(), headers))
      .rejects.toThrow(/bereikbaar/);
  });

  it('appends the filter query to the path', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    global.fetch = spy;
    await apiGet('http://x', '/api/analytics/summary',
                 { ...emptyFilters(), genre: ['Hardcore'] }, headers);
    expect(spy.mock.calls[0][0]).toBe('http://x/api/analytics/summary?genre=Hardcore');
  });

  it('merges extra parameters alongside the filters', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    global.fetch = spy;
    await apiGet('http://x', '/api/analytics/top-artists',
                 { ...emptyFilters(), genre: ['Terror'] }, headers, { limit: 5 });
    expect(spy.mock.calls[0][0]).toBe('http://x/api/analytics/top-artists?genre=Terror&limit=5');
  });

  it('omits the question mark when there is nothing to send', async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    global.fetch = spy;
    await apiGet('http://x', '/api/library/genres', {}, headers);
    expect(spy.mock.calls[0][0]).toBe('http://x/api/library/genres');
  });
});
