import { describe, it, expect } from "vitest";
import {
  equalizerSettings,
  EQUALIZER_DEFAULT,
  sanitizeEqualizerSettings,
} from "../../src/lib/store.js";
import { EQ_FREQUENCIES, EQ_PRESETS, CUSTOM_PRESET } from "../../src/lib/equalizerPresets.js";

describe("equalizer settings", () => {
  it("starts switched off and perfectly flat", () => {
    expect(EQUALIZER_DEFAULT).toEqual({
      enabled: false,
      preamp: 0,
      gains: Array.from({ length: EQ_FREQUENCIES.length }, () => 0),
      preset: "flat",
    });
  });

  it("persists changes to localStorage", () => {
    equalizerSettings.set({
      enabled: true,
      preamp: -3,
      gains: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      preset: CUSTOM_PRESET,
    });

    const stored = JSON.parse(localStorage.getItem("lms_equalizer"));
    expect(stored.enabled).toBe(true);
    expect(stored.preamp).toBe(-3);
    expect(stored.gains).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);

    equalizerSettings.set({ ...EQUALIZER_DEFAULT });
  });

  it("keeps a well-formed stored value intact", () => {
    const stored = {
      enabled: true,
      preamp: -2,
      gains: EQ_PRESETS.rock.gains.slice(),
      preset: "rock",
    };
    expect(sanitizeEqualizerSettings(stored)).toEqual(stored);
  });

  it("falls back to flat when the stored value makes no sense", () => {
    const wrecked = [
      null,
      "nonsense",
      42,
      {},
      { enabled: true, preamp: 0, gains: [1, 2, 3], preset: "flat" },
      { enabled: true, preamp: 0, gains: Array.from({ length: 10 }, () => "loud"), preset: "flat" },
      { enabled: true, preamp: 0, gains: Array.from({ length: 10 }, () => 999), preset: "flat" },
      { enabled: true, preamp: 999, gains: Array.from({ length: 10 }, () => 0), preset: "flat" },
      {
        enabled: true,
        preamp: 0,
        gains: Array.from({ length: 10 }, () => 0),
        preset: "disco-inferno",
      },
    ];
    for (const value of wrecked) {
      expect(sanitizeEqualizerSettings(value), JSON.stringify(value)).toEqual(EQUALIZER_DEFAULT);
    }
  });

  it("accepts custom as a preset name even though it has no curve", () => {
    const custom = {
      enabled: true,
      preamp: 0,
      gains: Array.from({ length: EQ_FREQUENCIES.length }, () => 1.5),
      preset: CUSTOM_PRESET,
    };
    expect(sanitizeEqualizerSettings(custom)).toEqual(custom);
  });

  it("coerces a non-boolean enabled flag rather than discarding the curve", () => {
    const result = sanitizeEqualizerSettings({
      enabled: "yes",
      preamp: -1,
      gains: EQ_PRESETS.jazz.gains.slice(),
      preset: "jazz",
    });
    expect(result.enabled).toBe(true);
    expect(result.gains).toEqual(EQ_PRESETS.jazz.gains);
  });
});
