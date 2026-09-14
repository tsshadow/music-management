import { describe, it, expect } from "vitest";
import {
  resolveDuration,
  progressPercent,
  formatHoursMinutes,
  formatClock,
} from "../../src/lib/playerProgress";

describe("resolveDuration", () => {
  it("trusts the audio element when it knows the length", () => {
    expect(resolveDuration(241.5, 240)).toBe(241.5);
  });

  it("falls back to the track length for an endless stream", () => {
    expect(resolveDuration(Infinity, 240)).toBe(240);
  });

  it("falls back to the track length before the metadata lands", () => {
    expect(resolveDuration(NaN, 240)).toBe(240);
  });

  it("falls back when the element reports a zero length", () => {
    expect(resolveDuration(0, 240)).toBe(240);
  });

  it("is zero when neither source has a length", () => {
    expect(resolveDuration(Infinity, undefined)).toBe(0);
    expect(resolveDuration(NaN, NaN)).toBe(0);
  });
});

describe("progressPercent", () => {
  it("is the share of the track that has played", () => {
    expect(progressPercent(60, 240)).toBe(25);
  });

  it("is zero without a usable length", () => {
    expect(progressPercent(60, 0)).toBe(0);
    expect(progressPercent(60, Infinity)).toBe(0);
    expect(progressPercent(60, NaN)).toBe(0);
  });

  it("is zero without a usable position", () => {
    expect(progressPercent(undefined, 240)).toBe(0);
    expect(progressPercent(NaN, 240)).toBe(0);
  });

  it("never runs past the end of the bar", () => {
    expect(progressPercent(300, 240)).toBe(100);
    expect(progressPercent(-5, 240)).toBe(0);
  });
});

describe("formatHoursMinutes", () => {
  it("drops the seconds -- the track list's own duration column in sets mode", () => {
    expect(formatHoursMinutes(4530)).toBe("1:15"); // 1h 15m 30s
    expect(formatHoursMinutes(600)).toBe("0:10");
  });

  it("pads a single-digit minute", () => {
    expect(formatHoursMinutes(3660)).toBe("1:01");
  });

  it("is 0:00 for nothing usable", () => {
    expect(formatHoursMinutes(NaN)).toBe("0:00");
    expect(formatHoursMinutes(-5)).toBe("0:00");
  });
});

describe("formatClock", () => {
  it("keeps the hour even under an hour, unlike formatTime's minutes-only read", () => {
    expect(formatClock(632)).toBe("0:10:32");
  });

  it("formats a two-hour set", () => {
    expect(formatClock(7825)).toBe("2:10:25");
  });

  it("pads single-digit minutes and seconds", () => {
    expect(formatClock(3661)).toBe("1:01:01");
  });

  it("is 0:00:00 for nothing usable", () => {
    expect(formatClock(NaN)).toBe("0:00:00");
    expect(formatClock(-5)).toBe("0:00:00");
    expect(formatClock(Infinity)).toBe("0:00:00");
  });
});
