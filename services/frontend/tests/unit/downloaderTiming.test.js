import { describe, it, expect } from 'vitest';
import {
  formatDuration,
  describeBackoff,
  changedValues,
} from '../../src/lib/management/downloaderTiming';

describe('formatDuration', () => {
  it('shows seconds below a minute', () => {
    expect(formatDuration(45)).toBe('45 sec');
  });

  it('shows whole minutes', () => {
    expect(formatDuration(900)).toBe('15 min');
  });

  it('shows whole hours', () => {
    expect(formatDuration(7200)).toBe('2 uur');
  });

  it('shows hours and minutes together', () => {
    expect(formatDuration(5400)).toBe('1 uur 30 min');
  });

  it('shows whole days', () => {
    expect(formatDuration(86400)).toBe('1 dag');
  });

  it('calls zero off', () => {
    expect(formatDuration(0)).toBe('uit');
  });

  it('survives a missing value', () => {
    expect(formatDuration(null)).toBe('—');
  });
});

describe('describeBackoff', () => {
  it('reports a quiet source as running at full speed', () => {
    const state = { multiplier: 1, cooldown_remaining: 0, last_429_at: null };
    expect(describeBackoff(state).tone).toBe('ok');
  });

  it('reports a slowed source as throttled', () => {
    const state = { multiplier: 4, cooldown_remaining: 0, last_429_at: '2026-07-30T12:00:00' };
    expect(describeBackoff(state).tone).toBe('slowed');
  });

  it('reports a parked source as waiting', () => {
    const state = { multiplier: 4, cooldown_remaining: 3600, last_429_at: '2026-07-30T12:00:00' };
    expect(describeBackoff(state).tone).toBe('parked');
  });

  it('names the multiplier when the source is slowed', () => {
    const state = { multiplier: 4, cooldown_remaining: 0, last_429_at: null };
    expect(describeBackoff(state).label).toContain('4x');
  });

  it('names the remaining wait when the source is parked', () => {
    const state = { multiplier: 2, cooldown_remaining: 1800, last_429_at: null };
    expect(describeBackoff(state).label).toContain('30 min');
  });

  it('survives a missing state', () => {
    expect(describeBackoff(null).tone).toBe('unknown');
  });
});

describe('changedValues', () => {
  const fields = [
    { key: 'sweep_interval', value: 900 },
    { key: 'burst_size', value: 5 },
  ];

  it('sends nothing when nothing was edited', () => {
    expect(changedValues(fields, { sweep_interval: 900, burst_size: 5 })).toEqual({});
  });

  it('sends only the knob that changed', () => {
    expect(changedValues(fields, { sweep_interval: 1800, burst_size: 5 })).toEqual({ sweep_interval: 1800 });
  });

  it('treats a numeric string from the input as its number', () => {
    expect(changedValues(fields, { sweep_interval: '900', burst_size: 5 })).toEqual({});
  });

  it('sends a changed value as a number', () => {
    expect(changedValues(fields, { sweep_interval: '1800', burst_size: 5 })).toEqual({ sweep_interval: 1800 });
  });

  it('ignores an empty input rather than sending a blank', () => {
    expect(changedValues(fields, { sweep_interval: '', burst_size: 5 })).toEqual({});
  });

  it('ignores a value that is not a number', () => {
    expect(changedValues(fields, { sweep_interval: 'soon', burst_size: 5 })).toEqual({});
  });
});
