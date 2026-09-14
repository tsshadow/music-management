import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { platform } from "../../src/lib/platform/index.js";
import {
  logAction,
  logError,
  describeError,
  identifyBundle,
} from "../../src/lib/diagnosticsLog.js";

/**
 * The one helper every screen calls to add a line to the action trail, and the
 * uncaught-error/identify plumbing built on top of it.
 *
 * `platform` is the real browser singleton in this test environment (there is
 * no `window.Capacitor`), so these tests monkey-patch its methods the same way
 * `deviceSettings.test.js` does, rather than mocking the whole module.
 */
describe("logAction", () => {
  const originalLog = platform.diagnostics.log;

  afterEach(() => {
    platform.diagnostics.log = originalLog;
  });

  it("forwards the action and detail to platform.diagnostics.log", () => {
    platform.diagnostics.log = vi.fn();

    logAction("player.play", { trackId: "42" });

    expect(platform.diagnostics.log).toHaveBeenCalledWith("player.play", { trackId: "42" });
  });

  it("works with no detail, the same as the contract allows", () => {
    platform.diagnostics.log = vi.fn();

    logAction("player.pause");

    expect(platform.diagnostics.log).toHaveBeenCalledWith("player.pause", undefined);
  });

  // The whole point: the action this call was reporting on must still have
  // happened even if diagnostics itself is broken.
  it("swallows an error thrown by platform.diagnostics.log", () => {
    platform.diagnostics.log = vi.fn(() => {
      throw new Error("bridge is gone");
    });
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    expect(() => logAction("player.play")).not.toThrow();
    expect(warnSpy).toHaveBeenCalled();

    warnSpy.mockRestore();
  });
});

describe("describeError", () => {
  it("keeps an Error's message and a flattened, bounded stack", () => {
    const error = new Error("boom");
    error.stack = "Error: boom\n    at foo (app.js:1:1)\n    at bar (app.js:2:2)";

    const detail = describeError(error);

    expect(detail.message).toBe("boom");
    expect(detail.stack).not.toContain("\n");
    expect(detail.stack).toContain("at foo");
  });

  it("truncates a very long stack rather than sending all of it", () => {
    const error = new Error("boom");
    error.stack = "x".repeat(5000);

    const detail = describeError(error);

    expect(detail.stack.length).toBeLessThanOrEqual(2000);
  });

  it("still has a message when the error carries no stack", () => {
    const error = new Error("boom");
    delete error.stack;

    expect(describeError(error)).toEqual({ message: "boom" });
  });

  it("turns a plain string rejection into a message", () => {
    expect(describeError("just a string")).toEqual({ message: "just a string" });
  });

  it("turns any other rejected value into a message rather than throwing", () => {
    expect(describeError({ code: 42 })).toEqual({ message: '{"code":42}' });
  });
});

describe("logError", () => {
  const originalIsNative = platform.system.isNative;
  const originalLog = platform.diagnostics.log;

  beforeEach(() => {
    platform.diagnostics.log = vi.fn();
  });

  afterEach(() => {
    platform.system.isNative = originalIsNative;
    platform.diagnostics.log = originalLog;
  });

  it("forwards to platform.diagnostics inside the shell", () => {
    platform.system.isNative = true;

    logError(new Error("boom"));

    expect(platform.diagnostics.log).toHaveBeenCalledWith(
      "js.error",
      expect.objectContaining({ message: "boom" }),
    );
  });

  it("tells an uncaught throw and a rejected promise apart", () => {
    platform.system.isNative = true;

    logError(new Error("rejected"), { action: "js.unhandledRejection" });

    expect(platform.diagnostics.log).toHaveBeenCalledWith(
      "js.unhandledRejection",
      expect.objectContaining({ message: "rejected" }),
    );
  });

  it("only logs to the console in a browser tab, never touching the ring", () => {
    platform.system.isNative = false;
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    logError(new Error("boom"));

    expect(platform.diagnostics.log).not.toHaveBeenCalled();
    expect(errorSpy).toHaveBeenCalled();

    errorSpy.mockRestore();
  });
});

describe("identifyBundle", () => {
  const originalIdentify = platform.diagnostics.identify;
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    platform.diagnostics.identify = originalIdentify;
    globalThis.fetch = originalFetch;
  });

  it("reads version.json and identifies with it and the user agent", async () => {
    platform.diagnostics.identify = vi.fn();
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ version: "abc1234" }),
    }));

    await identifyBundle();

    expect(platform.diagnostics.identify).toHaveBeenCalledWith({
      bundleVersion: "abc1234",
      userAgent: navigator.userAgent,
    });
  });

  it("identifies with a null version rather than failing when there is none", async () => {
    platform.diagnostics.identify = vi.fn();
    globalThis.fetch = vi.fn(async () => {
      throw new Error("no such file");
    });

    await identifyBundle();

    expect(platform.diagnostics.identify).toHaveBeenCalledWith(
      expect.objectContaining({ bundleVersion: null }),
    );
  });

  it("identifies with a null version when the server answers but not with one", async () => {
    platform.diagnostics.identify = vi.fn();
    globalThis.fetch = vi.fn(async () => ({ ok: false }));

    await identifyBundle();

    expect(platform.diagnostics.identify).toHaveBeenCalledWith(
      expect.objectContaining({ bundleVersion: null }),
    );
  });
});
