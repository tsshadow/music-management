import { describe, it, expect } from "vitest";
import {
  EQ_FREQUENCIES,
  EQ_Q,
  EQ_GAIN_MIN,
  EQ_GAIN_MAX,
  EQ_GAIN_STEP,
  EQ_PRESETS,
  EQ_PRESET_NAMES,
  CUSTOM_PRESET,
} from "../../src/lib/equalizerPresets.js";

describe("equalizer presets", () => {
  it("describes ten bands rising from sub-bass to treble", () => {
    expect(EQ_FREQUENCIES).toEqual([31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]);
    expect(EQ_Q).toBeGreaterThan(0);
  });

  it("keeps every preset within the slider range", () => {
    for (const [name, preset] of Object.entries(EQ_PRESETS)) {
      expect(preset.gains, name).toHaveLength(EQ_FREQUENCIES.length);
      for (const gain of preset.gains) {
        expect(Number.isFinite(gain), name).toBe(true);
        expect(gain, name).toBeGreaterThanOrEqual(EQ_GAIN_MIN);
        expect(gain, name).toBeLessThanOrEqual(EQ_GAIN_MAX);
      }
      expect(preset.preamp, name).toBeGreaterThanOrEqual(EQ_GAIN_MIN);
      expect(preset.preamp, name).toBeLessThanOrEqual(EQ_GAIN_MAX);
    }
  });

  it("holds back the preamp on presets that boost hard, so they cannot clip", () => {
    for (const [name, preset] of Object.entries(EQ_PRESETS)) {
      if (Math.max(...preset.gains) > 6) {
        expect(preset.preamp, name).toBeLessThan(0);
      }
    }
  });

  it("leaves flat completely untouched", () => {
    expect(EQ_PRESETS.flat.gains.every((g) => g === 0)).toBe(true);
    expect(EQ_PRESETS.flat.preamp).toBe(0);
  });

  it("lists every preset for display, and never lists custom as one", () => {
    expect(EQ_PRESET_NAMES).toEqual(Object.keys(EQ_PRESETS));
    expect(EQ_PRESET_NAMES).not.toContain(CUSTOM_PRESET);
    expect(EQ_PRESET_NAMES[0]).toBe("flat");
  });

  it("uses a slider step that divides the range evenly", () => {
    expect((EQ_GAIN_MAX - EQ_GAIN_MIN) % EQ_GAIN_STEP).toBe(0);
  });
});
