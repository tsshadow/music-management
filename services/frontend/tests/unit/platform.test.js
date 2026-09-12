import { describe, it, expect, beforeEach, vi } from "vitest";
import { platform, selectPlatform } from "../../src/lib/platform/index.js";
import browserPlayer from "../../src/lib/platform/browser/player.js";
import browserStorage from "../../src/lib/platform/browser/storage.js";
import browserSpeech from "../../src/lib/platform/browser/speech.js";
import browserDiagnostics, {
  createBrowserDiagnostics,
  CAPACITY,
} from "../../src/lib/platform/browser/diagnostics.js";
import browserSystem from "../../src/lib/platform/browser/system.js";
import { credentials, mumaApiUrl } from "../../src/lib/store.js";

describe("platform selection", () => {
  it("is the five members the UI is allowed to know about", () => {
    expect(Object.keys(platform).sort()).toEqual([
      "diagnostics",
      "player",
      "speech",
      "storage",
      "system",
    ]);
  });

  it("a plain browser tab gets the browser implementation", () => {
    const selected = selectPlatform({});

    expect(selected.player).toBe(browserPlayer);
    expect(selected.storage).toBe(browserStorage);
    expect(selected.speech).toBe(browserSpeech);
    expect(selected.diagnostics).toBe(browserDiagnostics);
    expect(selected.system).toBe(browserSystem);
  });

  // Until phase 1 ships its Kotlin plugins there is nothing else to choose, so
  // a shell falls through to the browser. This test is the marker for that: it
  // has to be rewritten the moment the Capacitor implementation lands, which is
  // exactly when someone should look at this line.
  it("a native shell falls through to the browser while there is nothing else", () => {
    const shell = { Capacitor: { isNativePlatform: () => true } };

    expect(selectPlatform(shell).player).toBe(browserPlayer);
  });

  it("a shell that is not running natively is a browser tab", () => {
    const shell = { Capacitor: { isNativePlatform: () => false } };

    expect(selectPlatform(shell).player).toBe(browserPlayer);
  });

  it("a host without a Capacitor global at all is not an error", () => {
    expect(() => selectPlatform(undefined)).not.toThrow();
    expect(selectPlatform(null).player).toBe(browserPlayer);
  });

  // One shared object, not one per caller: two playback engines alive at the
  // same time is the failure this design exists to prevent.
  it("everyone gets the same platform", () => {
    expect(selectPlatform({})).toBe(platform);
    expect(platform.player).toBe(browserPlayer);
  });
});

describe("browser storage", () => {
  it("says it cannot keep anything, which is what hides the downloads screen", () => {
    expect(browserStorage.supported).toBe(false);
  });

  it("answers a local query with an empty Subsonic body rather than throwing", async () => {
    const body = await browserStorage.query({ type: "album" });

    expect(body["subsonic-response"].status).toBe("ok");
  });

  it("refuses a download with a reason", async () => {
    await expect(browserStorage.download("song-1")).rejects.toThrow(/browser/);
  });

  it("has nothing downloaded", async () => {
    expect(await browserStorage.list()).toEqual([]);
    expect(await browserStorage.isLocal("song-1")).toBe(false);
    expect(await browserStorage.size()).toBe(0);
  });

  it("removing what is not there is not an error", async () => {
    await expect(browserStorage.remove("song-1")).resolves.toBeUndefined();
  });

  it("reports every id in a list as not downloaded", async () => {
    expect(await browserStorage.stateOf(["a", "b"])).toEqual({ a: "none", b: "none" });
    expect(await browserStorage.stateOf(undefined)).toEqual({});
  });

  it("hands back an unsubscribe that can be called", () => {
    expect(() => browserStorage.onProgress(() => {})()).not.toThrow();
  });
});

describe("browser speech", () => {
  it("is not available", async () => {
    expect(browserSpeech.supported).toBe(false);
    await expect(browserSpeech.start()).rejects.toThrow(/browser/);
  });

  it("stopping something that never started is not an error", () => {
    expect(() => browserSpeech.stop()).not.toThrow();
  });

  it("hands back unsubscribes that can be called", () => {
    expect(() => browserSpeech.onPartial(() => {})()).not.toThrow();
    expect(() => browserSpeech.onFinal(() => {})()).not.toThrow();
  });
});

describe("browser diagnostics", () => {
  let diagnostics;

  beforeEach(() => {
    diagnostics = createBrowserDiagnostics();
  });

  it("keeps what the user did, oldest first", () => {
    diagnostics.log("play");
    diagnostics.log("open:album", { id: "album-1" });

    expect(diagnostics.report().map((entry) => entry.action)).toEqual(["play", "open:album"]);
    expect(diagnostics.report()[1].detail).toEqual({ id: "album-1" });
  });

  it("keeps the last fifty and drops the rest", () => {
    for (let i = 0; i < CAPACITY + 10; i++) diagnostics.log(`action-${i}`);

    const report = diagnostics.report();
    expect(report).toHaveLength(CAPACITY);
    expect(report[0].action).toBe("action-10");
    expect(report.at(-1).action).toBe(`action-${CAPACITY + 9}`);
  });

  // The report travels into a crash report, where it is serialised and passed
  // around; a reader that edits it must not corrupt the buffer it came from.
  it("hands out a copy", () => {
    diagnostics.log("play");

    const report = diagnostics.report();
    report[0].action = "something else";

    expect(diagnostics.report()[0].action).toBe("play");
  });

  it("can be emptied", () => {
    diagnostics.log("play");
    diagnostics.clear();

    expect(diagnostics.report()).toEqual([]);
  });

  it("sends nothing anywhere", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    diagnostics.log("play");
    diagnostics.report();

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("browser system", () => {
  it("is not a native shell", () => {
    expect(browserSystem.isNative).toBe(false);
  });

  // The web resolves both bases in store.js, from window.location; this only
  // reads them back, so a change there cannot be undone here.
  it("reads the bases the web already resolved", () => {
    credentials.set({ url: "https://lms.example", username: "user", password: "pw" });
    mumaApiUrl.set("/muma");

    expect(browserSystem.serverUrl()).toEqual({
      subsonic: "https://lms.example",
      mumaApi: "/muma",
    });
  });

  it("has no platform events, but every subscription can be undone", () => {
    const handler = vi.fn();

    browserSystem.onBack(handler)();
    browserSystem.onDeepLink(handler)();
    browserSystem.carConnected(handler)();

    expect(handler).not.toHaveBeenCalled();
  });
});
