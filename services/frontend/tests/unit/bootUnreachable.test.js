import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import { askServerDecision } from "../../src/lib/bootUnreachable.js";
import { t } from "../../src/lib/i18n/index.js";

/**
 * The boot screen's server-unreachable panel (docs/designs/app-start-reachability/): three ways
 * on -- try again, wait for the server, continue offline -- drawn on the boot screen before the
 * app mounts.
 */

function paintBootScreen() {
  document.body.innerHTML = `
    <div id="boot-screen">
      <p data-boot-stage></p>
      <div class="boot-track"><div data-boot-bar></div></div>
      <p data-boot-hint></p>
      <button data-boot-retry></button>
    </div>`;
  return document.getElementById("boot-screen");
}

const button = (action) => document.querySelector(`[data-boot-action="${action}"]`);
const text = (selector) => document.querySelector(selector)?.textContent ?? "";
const tr = (key, vars) => get(t)(key, vars);
/** Lets the awaited `localeReady()` and click handlers settle. */
const settle = () => vi.advanceTimersByTimeAsync(0);

describe("askServerDecision", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("names the problem and offers all three ways on", async () => {
    const screen = paintBootScreen();
    const decision = askServerDecision({ state: "unreachable" }, { check: vi.fn() });
    await settle();

    expect(screen.classList.contains("boot-choosing")).toBe(true);
    expect(text(".boot-choice-title")).toBe(tr("boot.reachability.unreachableTitle"));
    expect(button("retry").textContent).toBe(tr("boot.reachability.retry"));
    expect(button("wait").textContent).toBe(tr("boot.reachability.wait"));
    expect(button("offline").textContent).toBe(tr("boot.reachability.continueOffline"));

    button("offline").click();
    await expect(decision).resolves.toBe("offline");
    expect(screen.classList.contains("boot-choosing")).toBe(false);
    expect(document.querySelector("[data-boot-choice]")).toBeNull();
  });

  it("says when there is no network at all", async () => {
    paintBootScreen();
    askServerDecision({ state: "noNetwork" }, { check: vi.fn() });
    await settle();
    expect(text(".boot-choice-title")).toBe(tr("boot.reachability.noNetworkTitle"));
  });

  it("goes online when a retry reaches the server, and stays when it does not", async () => {
    paintBootScreen();
    const check = vi
      .fn()
      .mockResolvedValueOnce({ state: "noNetwork" })
      .mockResolvedValueOnce({ state: "reachable" });
    const decision = askServerDecision({ state: "unreachable" }, { check });
    await settle();

    button("retry").click();
    await settle();
    expect(check).toHaveBeenCalledTimes(1);
    expect(text(".boot-choice-title")).toBe(tr("boot.reachability.noNetworkTitle"));
    expect(button("retry").disabled).toBe(false);

    button("retry").click();
    await expect(decision).resolves.toBe("online");
  });

  it("treats a refused password as online, so the login page takes over", async () => {
    paintBootScreen();
    const decision = askServerDecision(
      { state: "unreachable" },
      { check: vi.fn().mockResolvedValue({ state: "authFailed" }) },
    );
    await settle();
    button("retry").click();
    await expect(decision).resolves.toBe("online");
  });

  it("waits calmly, shows since when and the next attempt, and continues once the server answers", async () => {
    paintBootScreen();
    const check = vi
      .fn()
      .mockResolvedValueOnce({ state: "unreachable" })
      .mockResolvedValueOnce({ state: "reachable" });
    const decision = askServerDecision({ state: "unreachable" }, { check });
    await settle();

    button("wait").click();
    await settle();
    expect(text(".boot-choice-title")).toBe(tr("boot.reachability.waitingTitle"));
    expect(button("wait").hidden).toBe(true);
    expect(button("offline").hidden).toBe(false);
    expect(text(".boot-choice-status")).toBe(tr("boot.reachability.nextAttempt", { seconds: 2 }));
    expect(check).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(2000);
    expect(check).toHaveBeenCalledTimes(1);
    expect(text(".boot-choice-status")).toBe(tr("boot.reachability.nextAttempt", { seconds: 5 }));

    await vi.advanceTimersByTimeAsync(5000);
    await expect(decision).resolves.toBe("online");
    expect(check).toHaveBeenCalledTimes(2);
  });

  it("lets the listener give up waiting and go offline at any time", async () => {
    paintBootScreen();
    const check = vi.fn().mockResolvedValue({ state: "unreachable" });
    const decision = askServerDecision({ state: "unreachable" }, { check });
    await settle();
    button("wait").click();
    await vi.advanceTimersByTimeAsync(2000);
    button("offline").click();
    await expect(decision).resolves.toBe("offline");
    await vi.advanceTimersByTimeAsync(60000);
    expect(check).toHaveBeenCalledTimes(1);
  });

  it("tries at once when the phone reports a network", async () => {
    paintBootScreen();
    let fire;
    const platform = {
      storage: {
        onConnectivity: (handler) => {
          fire = handler;
          return () => {};
        },
      },
    };
    const check = vi.fn().mockResolvedValue({ state: "reachable" });
    const decision = askServerDecision({ state: "noNetwork" }, { check, platform });
    await settle();
    button("wait").click();
    fire({ online: true });
    await expect(decision).resolves.toBe("online");
  });

  it("starts offline rather than hang when there is no boot screen to ask on", async () => {
    document.body.innerHTML = "";
    const decision = askServerDecision({ state: "unreachable" }, { check: vi.fn() });
    await expect(decision).resolves.toBe("offline");
  });
});
