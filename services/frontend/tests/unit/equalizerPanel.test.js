import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import Equalizer from "../../src/lib/Equalizer.svelte";
import { equalizerSettings, EQUALIZER_DEFAULT } from "../../src/lib/store.js";
import { EQ_FREQUENCIES, EQ_PRESETS, CUSTOM_PRESET } from "../../src/lib/equalizerPresets.js";

describe("Equalizer panel", () => {
  beforeEach(() => {
    equalizerSettings.set({ ...EQUALIZER_DEFAULT, gains: EQUALIZER_DEFAULT.gains.slice() });
  });

  it("renders one slider per band plus the pre-amp", () => {
    render(Equalizer, {});
    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(EQ_FREQUENCIES.length + 1);
  });

  it("switches the equalizer on", async () => {
    render(Equalizer, {});
    await fireEvent.click(screen.getByLabelText("Equalizer aan"));
    expect(get(equalizerSettings).enabled).toBe(true);
  });

  it("writes a whole curve when a preset is chosen", async () => {
    render(Equalizer, {});
    await fireEvent.change(screen.getByLabelText("Voorinstelling"), { target: { value: "rock" } });

    const settings = get(equalizerSettings);
    expect(settings.preset).toBe("rock");
    expect(settings.gains).toEqual(EQ_PRESETS.rock.gains);
    expect(settings.preamp).toBe(EQ_PRESETS.rock.preamp);
  });

  it("drops out of the preset as soon as a band is moved by hand", async () => {
    equalizerSettings.set({
      enabled: true,
      preamp: EQ_PRESETS.rock.preamp,
      gains: EQ_PRESETS.rock.gains.slice(),
      preset: "rock",
    });
    render(Equalizer, {});

    const bandSlider = screen.getByLabelText(/31/);
    await fireEvent.input(bandSlider, { target: { value: "-6" } });

    const settings = get(equalizerSettings);
    expect(settings.preset).toBe(CUSTOM_PRESET);
    expect(settings.gains[0]).toBe(-6);
    expect(settings.gains[1]).toBe(EQ_PRESETS.rock.gains[1]);
  });

  it("keeps the preset when the pre-amp alone is moved", async () => {
    equalizerSettings.set({
      enabled: true,
      preamp: 0,
      gains: EQ_PRESETS.rock.gains.slice(),
      preset: "rock",
    });
    render(Equalizer, {});

    await fireEvent.input(screen.getByLabelText("Voorversterking"), { target: { value: "-4.5" } });

    const settings = get(equalizerSettings);
    expect(settings.preamp).toBe(-4.5);
    expect(settings.preset).toBe("rock");
  });

  it("returns everything to flat on reset, without switching itself off", async () => {
    equalizerSettings.set({
      enabled: true,
      preamp: -3,
      gains: EQ_PRESETS.bassBoost.gains.slice(),
      preset: "bassBoost",
    });
    render(Equalizer, {});

    await fireEvent.click(screen.getByText("Herstellen"));

    const settings = get(equalizerSettings);
    expect(settings.gains).toEqual(Array.from({ length: EQ_FREQUENCIES.length }, () => 0));
    expect(settings.preamp).toBe(0);
    expect(settings.preset).toBe("flat");
    expect(settings.enabled).toBe(true);
  });

  it("closes on the close button and on Escape", async () => {
    let closed = 0;
    render(Equalizer, {
      onclose: () => {
        closed += 1;
      },
    });

    await fireEvent.click(screen.getByLabelText("Equalizer sluiten"));
    expect(closed).toBe(1);

    await fireEvent.keyDown(window, { key: "Escape" });
    expect(closed).toBe(2);
  });
});
