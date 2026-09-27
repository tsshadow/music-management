import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  BOOT_FADE_MS,
  BOOT_SLOW_AFTER_MS,
  dismissBootScreen,
  setBootStage,
} from "../../src/lib/bootScreen.js";

/** The markup index.html paints before the bundle runs. */
function paintBootScreen() {
  document.body.innerHTML = `
    <div id="boot-screen">
      <p data-boot-stage></p>
      <div><div data-boot-bar></div></div>
      <p data-boot-hint></p>
      <button data-boot-retry></button>
    </div>
    <div id="app"></div>`;
  return document.getElementById("boot-screen");
}

/** The boot screen's stages, hint and removal (docs/designs/perceived-performance/). */
describe("bootScreen", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(async () => {
    // Resets the module's stage memory for the next test.
    const done = dismissBootScreen();
    vi.runAllTimers();
    await done;
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("names the stage in the listener's language", () => {
    const screen = paintBootScreen();

    setBootStage("connecting");
    expect(screen.querySelector("[data-boot-stage]").textContent).toBe("Verbinden met de server…");

    setBootStage("signingIn");
    expect(screen.querySelector("[data-boot-stage]").textContent).toBe("Inloggen…");
  });

  it("fills the bar when the stage has a count, and slides again when it has none", () => {
    const screen = paintBootScreen();
    const bar = screen.querySelector("[data-boot-bar]");

    setBootStage("restoringQueue", { done: 1, total: 4 });
    expect(bar.classList.contains("boot-determinate")).toBe(true);
    expect(bar.style.width).toBe("25%");

    setBootStage("starting");
    expect(bar.classList.contains("boot-determinate")).toBe(false);
    expect(bar.style.width).toBe("");
  });

  it("says it is taking longer than usual after one stage has lasted long", () => {
    const screen = paintBootScreen();
    const hint = screen.querySelector("[data-boot-hint]");

    setBootStage("connecting");
    vi.advanceTimersByTime(BOOT_SLOW_AFTER_MS - 1);
    expect(hint.textContent).toBe("");
    vi.advanceTimersByTime(1);
    expect(hint.textContent).toBe("Dit duurt langer dan normaal");

    // A new stage starts its own clock and clears the hint.
    setBootStage("signingIn");
    expect(hint.textContent).toBe("");
  });

  it("progress within a stage does not restart the hint's clock", () => {
    const screen = paintBootScreen();
    const hint = screen.querySelector("[data-boot-hint]");

    setBootStage("restoringQueue", { done: 0, total: 10 });
    vi.advanceTimersByTime(BOOT_SLOW_AFTER_MS / 2);
    setBootStage("restoringQueue", { done: 5, total: 10 });
    vi.advanceTimersByTime(BOOT_SLOW_AFTER_MS / 2);

    expect(hint.textContent).toBe("Dit duurt langer dan normaal");
  });

  it("fades out and removes itself, and stops the page's retry offer", async () => {
    const screen = paintBootScreen();
    window.__mumaBootTimer = setTimeout(() => {}, 20_000);

    const done = dismissBootScreen();
    expect(screen.classList.contains("boot-leaving")).toBe(true);
    expect(window.__mumaBootDone).toBe(true);
    vi.advanceTimersByTime(BOOT_FADE_MS);
    await done;

    expect(document.getElementById("boot-screen")).toBeNull();
    expect(document.getElementById("app")).not.toBeNull();
  });

  it("does nothing at all when there is no boot screen", async () => {
    expect(() => setBootStage("connecting")).not.toThrow();
    await expect(dismissBootScreen()).resolves.toBeUndefined();
  });
});
