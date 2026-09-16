import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import SetupWizard from "../../src/lib/SetupWizard.svelte";
import { SETUP_STEPS } from "../../src/lib/setup.js";
import { setupStepsSeen, viewMode, homeModeReleaseRadar } from "../../src/lib/store.js";

const BROWSER = { storage: { supported: false }, system: {} };
const NATIVE = {
  storage: { supported: true },
  system: {
    getSettings: vi.fn(async () => ({ wifiOnly: true })),
    setSetting: vi.fn(async () => {}),
  },
};

const steps = (...ids) => SETUP_STEPS.filter((step) => ids.includes(step.id));

describe("SetupWizard", () => {
  beforeEach(() => {
    setupStepsSeen.set([]);
    viewMode.set("songs");
    homeModeReleaseRadar.set("BUTTON");
  });

  it("welcomes a first run and walks the steps in order", async () => {
    render(SetupWizard, { steps: steps("language", "mode", "guide"), platform: BROWSER });

    expect(screen.getByText("Welkom bij MuMa")).toBeTruthy();
    expect(screen.getByText("Stap 1 van 3")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "In welke taal?" })).toBeTruthy();
    expect(screen.queryByText("Nieuw")).toBeNull();

    await fireEvent.click(screen.getByRole("button", { name: "Volgende" }));
    expect(screen.getByRole("heading", { name: "Nummers of sets?" })).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Terug" }));
    expect(screen.getByRole("heading", { name: "In welke taal?" })).toBeTruthy();
  });

  it("badges an update run as new", () => {
    render(SetupWizard, { steps: steps("home"), update: true, platform: BROWSER });

    expect(screen.getByText("Nieuw sinds je laatste bezoek")).toBeTruthy();
    expect(screen.getByText("Nieuw")).toBeTruthy();
  });

  it("records every walked step and closes on Done", async () => {
    const onclose = vi.fn();
    setupStepsSeen.set(["language"]);
    render(SetupWizard, { steps: steps("mode", "guide"), platform: BROWSER, onclose });

    await fireEvent.click(screen.getByRole("button", { name: "Volgende" }));
    await fireEvent.click(screen.getByRole("button", { name: "Klaar" }));

    expect(get(setupStepsSeen)).toEqual(["language", "mode", "guide"]);
    expect(onclose).toHaveBeenCalledWith(undefined);
  });

  // A tour that came back until it was completed would be a nag, not a welcome.
  it("records the steps on Skip too, so it never reopens on its own", async () => {
    const onclose = vi.fn();
    render(SetupWizard, { steps: steps("language", "mode"), platform: BROWSER, onclose });

    await fireEvent.click(screen.getByRole("button", { name: "Overslaan" }));

    expect(get(setupStepsSeen)).toEqual(["language", "mode"]);
    expect(onclose).toHaveBeenCalled();
  });

  it("writes the same stores the settings pages write", async () => {
    render(SetupWizard, { steps: steps("mode", "home"), platform: BROWSER });

    await fireEvent.click(screen.getByRole("button", { name: "Sets" }));
    expect(get(viewMode)).toBe("sets");

    await fireEvent.click(screen.getByRole("button", { name: "Volgende" }));
    await fireEvent.change(screen.getByLabelText("Release Radar"), {
      target: { value: "OVERVIEW" },
    });
    expect(get(homeModeReleaseRadar)).toBe("OVERVIEW");
  });

  it("reads and writes the phone's wifi-only setting through the shell", async () => {
    render(SetupWizard, { steps: steps("downloads"), platform: NATIVE });

    const box = await screen.findByRole("checkbox");
    expect(box.checked).toBe(true);

    await fireEvent.click(box);
    expect(NATIVE.system.setSetting).toHaveBeenCalledWith({ key: "wifiOnly", value: false });
  });

  it("hands over to the manual from the last step", async () => {
    const onclose = vi.fn();
    render(SetupWizard, { steps: steps("guide"), platform: BROWSER, onclose });

    await fireEvent.click(screen.getByRole("button", { name: "Handleiding openen" }));

    expect(get(setupStepsSeen)).toEqual(["guide"]);
    expect(onclose).toHaveBeenCalledWith("help");
  });

  it("says so when there is nothing left to walk through", () => {
    render(SetupWizard, { steps: [], platform: BROWSER });

    expect(screen.getByText("Alles is al ingesteld")).toBeTruthy();
  });
});
