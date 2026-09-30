import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  checkServer,
  isUnreachable,
  REACHABILITY,
  retryDelayMs,
  RETRY_DELAYS_MS,
  waitForServer,
} from "../../src/lib/serverReachability.js";

/**
 * The start-up check and the "Wachten op server" loop (docs/designs/app-start-reachability/).
 * The classification itself is native (ServerReachabilityTest.kt); this side has to fail open,
 * back off, and never run two attempts at once.
 */

/** A shell whose `checkServer` answers the given states in turn. */
function shellAnswering(...states) {
  const answers = [...states];
  return {
    storage: {
      supported: true,
      checkServer: vi.fn(async () => ({ state: answers.shift() ?? "reachable", elapsedMs: 42 })),
    },
  };
}

describe("checkServer", () => {
  it("passes the native answer through", async () => {
    const shell = shellAnswering("unreachable");
    const result = await checkServer(shell);
    expect(result).toEqual({
      state: "unreachable",
      elapsedMs: 42,
      offlineChosen: false,
      skipped: false,
    });
    expect(shell.storage.checkServer).toHaveBeenCalledWith({ timeoutMs: 3000 });
  });

  it("fails open when the shell has no check, it throws, or answers nonsense", async () => {
    expect((await checkServer({ storage: { supported: false } })).state).toBe("reachable");
    expect((await checkServer({ storage: { supported: true } })).skipped).toBe(true);
    const throwing = {
      storage: {
        supported: true,
        checkServer: vi.fn(async () => {
          throw new Error("bridge");
        }),
      },
    };
    vi.spyOn(console, "warn").mockImplementation(() => {});
    expect((await checkServer(throwing)).state).toBe("reachable");
    expect((await checkServer(shellAnswering("sideways"))).state).toBe("reachable");
  });

  it("stops the start only for no network and an unreachable server", () => {
    expect(isUnreachable(REACHABILITY.NO_NETWORK)).toBe(true);
    expect(isUnreachable(REACHABILITY.UNREACHABLE)).toBe(true);
    expect(isUnreachable(REACHABILITY.REACHABLE)).toBe(false);
    // A refused password is the login page's business, not "offline".
    expect(isUnreachable(REACHABILITY.AUTH_FAILED)).toBe(false);
  });
});

describe("retryDelayMs", () => {
  it("backs off 2, 5, 10, 20 s and then stays at 30 s", () => {
    expect([0, 1, 2, 3, 4, 5, 50].map(retryDelayMs)).toEqual([
      2000, 5000, 10000, 20000, 30000, 30000, 30000,
    ]);
    expect(retryDelayMs(-3)).toBe(RETRY_DELAYS_MS[0]);
  });
});

describe("waitForServer", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("retries on the backoff schedule until the server answers", async () => {
    const check = vi
      .fn()
      .mockResolvedValueOnce({ state: "unreachable" })
      .mockResolvedValueOnce({ state: "noNetwork" })
      .mockResolvedValueOnce({ state: "reachable" });
    const updates = [];
    const waiter = waitForServer({ check, onUpdate: (u) => updates.push(u) });

    await vi.advanceTimersByTimeAsync(1999);
    expect(check).toHaveBeenCalledTimes(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(check).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(5000);
    expect(check).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(10000);
    expect(check).toHaveBeenCalledTimes(3);
    await expect(waiter.promise).resolves.toEqual({ state: "reachable" });
    expect(updates.some((u) => u.checking === true)).toBe(true);
    expect(updates.filter((u) => u.nextAttemptAt).length).toBe(3);
  });

  it("tries at once when a network comes up, and only then", async () => {
    let fire;
    const check = vi.fn().mockResolvedValue({ state: "reachable" });
    const waiter = waitForServer({
      check,
      onConnectivity: (handler) => {
        fire = handler;
        return () => {};
      },
    });
    fire({ online: false });
    expect(check).not.toHaveBeenCalled();
    fire({ online: true });
    await expect(waiter.promise).resolves.toEqual({ state: "reachable" });
    expect(check).toHaveBeenCalledTimes(1);
  });

  it("with anyChange, tries on every network change", async () => {
    let fire;
    const check = vi.fn().mockResolvedValue({ state: "reachable" });
    const waiter = waitForServer({
      check,
      anyChange: true,
      onConnectivity: (handler) => {
        fire = handler;
        return () => {};
      },
    });
    fire({ online: false });
    await expect(waiter.promise).resolves.toEqual({ state: "reachable" });
  });

  it("ends on an auth failure too, so the login page can take over", async () => {
    const waiter = waitForServer({ check: vi.fn().mockResolvedValue({ state: "authFailed" }) });
    await vi.advanceTimersByTimeAsync(2000);
    await expect(waiter.promise).resolves.toEqual({ state: "authFailed" });
  });

  it("never runs two attempts at once", async () => {
    let release;
    const check = vi.fn(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    const waiter = waitForServer({ check });
    waiter.retryNow();
    waiter.retryNow();
    expect(check).toHaveBeenCalledTimes(1);
    release({ state: "reachable" });
    await expect(waiter.promise).resolves.toEqual({ state: "reachable" });
  });

  it("resolves null and stops following connectivity when cancelled", async () => {
    const unsubscribe = vi.fn();
    const check = vi.fn();
    const waiter = waitForServer({ check, onConnectivity: () => unsubscribe });
    waiter.cancel();
    await expect(waiter.promise).resolves.toBeNull();
    await vi.advanceTimersByTimeAsync(60000);
    expect(check).not.toHaveBeenCalled();
    expect(unsubscribe).toHaveBeenCalled();
  });
});
