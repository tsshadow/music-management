import { describe, it, expect, beforeEach, vi } from "vitest";
import { get } from "svelte/store";
import { equalizerSettings, EQUALIZER_DEFAULT } from "../../src/lib/store.js";
import * as equalizer from "../../src/lib/equalizer.js";
import { EQ_PRESETS } from "../../src/lib/equalizerPresets.js";

/**
 * Mirrors the single $effect in Player.svelte. If the player's version and this
 * one drift apart, this test stops protecting anything -- keep them identical.
 */
function applySettings(settings, element) {
  if (!settings.enabled) {
    equalizer.setEnabled(false);
    return;
  }
  if (!equalizer.attach(element)) return;
  equalizer.setGains(settings.gains);
  equalizer.setPreamp(settings.preamp);
  equalizer.setEnabled(true);
}

function makeFakeContext() {
  const nodes = [];
  const make = (kind) => {
    const node = { kind, connect() {}, disconnect() {} };
    nodes.push(node);
    return node;
  };
  return {
    state: "running",
    destination: { connect() {} },
    nodes,
    resume: vi.fn(),
    createMediaElementSource: vi.fn(() => make("source")),
    createGain: vi.fn(() => Object.assign(make("gain"), { gain: { value: 1 } })),
    createBiquadFilter: vi.fn(() =>
      Object.assign(make("filter"), {
        type: "",
        frequency: { value: 0 },
        Q: { value: 0 },
        gain: { value: 0 },
      }),
    ),
  };
}

describe("player wiring", () => {
  let context;
  const element = {};

  beforeEach(() => {
    equalizer.__resetForTests();
    context = makeFakeContext();
    equalizer.__setContextFactoryForTests(() => context);
    equalizerSettings.set({ ...EQUALIZER_DEFAULT, gains: EQUALIZER_DEFAULT.gains.slice() });
  });

  it("builds no audio graph for a listener who never turns the equalizer on", () => {
    applySettings(get(equalizerSettings), element);
    expect(context.createMediaElementSource).not.toHaveBeenCalled();
  });

  it("builds the graph on the first switch-on and pushes the curve through", () => {
    equalizerSettings.set({
      enabled: true,
      preamp: EQ_PRESETS.rock.preamp,
      gains: EQ_PRESETS.rock.gains.slice(),
      preset: "rock",
    });
    applySettings(get(equalizerSettings), element);

    expect(context.createMediaElementSource).toHaveBeenCalledTimes(1);
    const filters = context.nodes.filter((n) => n.kind === "filter");
    expect(filters.map((f) => f.gain.value)).toEqual(EQ_PRESETS.rock.gains);
  });

  it("flattens the graph when the listener switches it off again, keeping it built", () => {
    equalizerSettings.set({
      enabled: true,
      preamp: -2,
      gains: EQ_PRESETS.rock.gains.slice(),
      preset: "rock",
    });
    applySettings(get(equalizerSettings), element);

    equalizerSettings.update((s) => ({ ...s, enabled: false }));
    applySettings(get(equalizerSettings), element);

    const filters = context.nodes.filter((n) => n.kind === "filter");
    expect(filters.every((f) => f.gain.value === 0)).toBe(true);
    expect(context.createMediaElementSource).toHaveBeenCalledTimes(1);
  });

  it("leaves playback alone when the graph refuses to build", () => {
    equalizer.__resetForTests();
    const broken = makeFakeContext();
    broken.createMediaElementSource = vi.fn(() => {
      throw new Error("no");
    });
    equalizer.__setContextFactoryForTests(() => broken);
    vi.spyOn(console, "error").mockImplementation(() => {});

    equalizerSettings.set({
      enabled: true,
      preamp: 0,
      gains: EQ_PRESETS.pop.gains.slice(),
      preset: "pop",
    });
    expect(() => applySettings(get(equalizerSettings), element)).not.toThrow();
  });
});
