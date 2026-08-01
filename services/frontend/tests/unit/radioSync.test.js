import { describe, it, expect } from 'vitest';
import {
  medianClockOffset,
  targetPosition,
  correction,
  HARD_SEEK_THRESHOLD,
  DEADBAND,
} from '../../src/lib/radioSync';

describe('medianClockOffset', () => {
  it('returns 0 for no samples', () => {
    expect(medianClockOffset([])).toBe(0);
  });

  it('computes offset from the midpoint of the round trip', () => {
    // Request sent at 1000, answered at 1200, server said 1600 => midpoint 1100, offset 500.
    expect(medianClockOffset([{ t0: 1000, t1: 1200, serverTime: 1600 }])).toBe(500);
  });

  it('takes the median so one slow round trip cannot skew it', () => {
    const samples = [
      { t0: 0, t1: 100, serverTime: 1050 },   // offset 1000
      { t0: 0, t1: 100, serverTime: 1060 },   // offset 1010
      { t0: 0, t1: 4000, serverTime: 3990 },  // offset 1990 (outlier)
    ];
    expect(medianClockOffset(samples)).toBe(1010);
  });

  it('averages the two middle values for an even sample count', () => {
    const samples = [
      { t0: 0, t1: 0, serverTime: 100 },
      { t0: 0, t1: 0, serverTime: 200 },
    ];
    expect(medianClockOffset(samples)).toBe(150);
  });
});

describe('targetPosition', () => {
  it('returns seconds elapsed since the entry started', () => {
    expect(targetPosition({ startedAtMs: 1_000_000 }, 1_030_000)).toBe(30);
  });

  it('returns a negative value for an entry that has not started yet', () => {
    expect(targetPosition({ startedAtMs: 1_000_000 }, 999_000)).toBe(-1);
  });
});

describe('correction', () => {
  it('does nothing inside the deadband', () => {
    expect(correction(10, 10.1)).toEqual({ action: 'none', rate: 1 });
  });

  it('hard seeks when the error exceeds the threshold', () => {
    const result = correction(10, 20);
    expect(result.action).toBe('seek');
    expect(result.position).toBe(20);
    expect(result.rate).toBe(1);
  });

  it('hard seeks when running ahead by more than the threshold', () => {
    expect(correction(30, 10).action).toBe('seek');
  });

  it('speeds up slightly when behind', () => {
    const result = correction(10, 11);
    expect(result.action).toBe('rate');
    expect(result.rate).toBeGreaterThan(1);
    expect(result.rate).toBeLessThanOrEqual(1.02);
  });

  it('slows down slightly when ahead', () => {
    const result = correction(11, 10);
    expect(result.action).toBe('rate');
    expect(result.rate).toBeLessThan(1);
    expect(result.rate).toBeGreaterThanOrEqual(0.98);
  });

  it('clamps the rate at the boundaries', () => {
    expect(correction(0, HARD_SEEK_THRESHOLD - 0.01).rate).toBeLessThanOrEqual(1.02);
    expect(correction(HARD_SEEK_THRESHOLD - 0.01, 0).rate).toBeGreaterThanOrEqual(0.98);
  });

  it('exposes its thresholds', () => {
    expect(HARD_SEEK_THRESHOLD).toBe(3.0);
    expect(DEADBAND).toBe(0.15);
  });
});
