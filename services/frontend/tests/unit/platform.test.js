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
import { createCapacitorStorage } from "../../src/lib/platform/capacitor/storage.js";
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

  it("a native shell gets the Capacitor implementation instead", () => {
    const shell = { Capacitor: { isNativePlatform: () => true } };

    const selected = selectPlatform(shell);

    expect(selected.player).not.toBe(browserPlayer);
    expect(selected.player.ownsQueue).toBe(true);
    expect(selected.system.isNative).toBe(true);
  });

  // Two playback engines alive at once is the failure this design exists to
  // prevent, and a second call that built a second set would be exactly that.
  it("builds the shell implementation once", () => {
    const shell = { Capacitor: { isNativePlatform: () => true } };

    expect(selectPlatform(shell)).toBe(selectPlatform(shell));
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

describe("browser player queue", () => {
  // Not because a browser has a platform queue -- it has none -- but so that
  // the queue logic can call these without first asking which shell it is in.
  it("says the queue is the UI's, and answers the queue calls with nothing", async () => {
    expect(browserPlayer.ownsQueue).toBe(false);
    expect(await browserPlayer.setQueue({ tracks: [{ id: "1" }], index: 0 })).toEqual({
      index: -1,
      length: 0,
      trackIds: [],
    });
    expect(await browserPlayer.queueState()).toEqual({ index: -1, length: 0, trackIds: [] });
  });

  it("accepts a subscription to the event only a platform service sends", () => {
    const handler = vi.fn();

    expect(() => browserPlayer.on("command", handler)()).not.toThrow();
    expect(handler).not.toHaveBeenCalled();
  });

  // A browser has no service to ask; the queue in Player.svelte already advances itself and
  // never calls these, but a caller that branches on isNative rather than ownsQueue must still
  // find a function here rather than crash on undefined.
  it("has next and previous, and neither does anything", () => {
    expect(() => browserPlayer.next()).not.toThrow();
    expect(() => browserPlayer.previous()).not.toThrow();
  });

  it("takes a rating and does nothing with it: a tab has no service queue", async () => {
    await expect(browserPlayer.setRating("1", 4)).resolves.toBeUndefined();
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

  it("clearCache is a no-op that resolves", async () => {
    await expect(browserStorage.clearCache()).resolves.toBeUndefined();
  });

  it("has no rating queue: queueRating answers false", async () => {
    expect(await browserStorage.queueRating("song-1", 4)).toBe(false);
  });
});

describe("capacitor storage: the rating queue", () => {
  it("hands the rating to the plugin and reports it queued", async () => {
    const plugin = { queueRating: vi.fn(async () => ({ queued: true })) };
    const storage = createCapacitorStorage(plugin);

    expect(await storage.queueRating(12, 0)).toBe(true);
    expect(plugin.queueRating).toHaveBeenCalledWith({ id: "12", rating: 0 });
  });

  it("answers false when the APK has no queue", async () => {
    expect(await createCapacitorStorage({}).queueRating("12", 3)).toBe(false);
    expect(
      await createCapacitorStorage({ queueRating: vi.fn(async () => ({})) }).queueRating("12", 3),
    ).toBe(false);
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

  it("rejects interpret the same way it rejects start", async () => {
    await expect(browserSpeech.interpret({ text: "speel hardstyle af" })).rejects.toThrow(
      /browser/,
    );
  });

  it("answers vocabulary and trace empty rather than throwing", async () => {
    await expect(browserSpeech.vocabulary()).resolves.toEqual({ title: "", html: "" });
    await expect(browserSpeech.trace()).resolves.toEqual({ traces: [] });
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

  // There is no report here to attach a bundle version or a user agent to,
  // so a call site never needs a platform check around `identify`.
  it("has nothing to identify to and does not throw", () => {
    expect(() =>
      diagnostics.identify({ bundleVersion: "abc1234", userAgent: "Mozilla/5.0" }),
    ).not.toThrow();
    expect(() => diagnostics.identify()).not.toThrow();
  });
});

describe("browser system", () => {
  it("is not a native shell", () => {
    expect(browserSystem.isNative).toBe(false);
  });

  // A browser tab is not an APK and always runs the latest served bundle --
  // mobileReleaseNotes.js reads a blank appVersion as "nothing to compare".
  it("has no app version of its own to report", async () => {
    await expect(browserSystem.appVersion()).resolves.toBe("");
  });

  it("has no APK to describe or to update", async () => {
    await expect(browserSystem.appInfo()).resolves.toBeNull();
    await expect(browserSystem.checkForUpdate()).rejects.toThrow(/no APK/);
  });

  it("opens a url in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);

    await browserSystem.openUrl("https://apk.example/dl/313");

    expect(open).toHaveBeenCalledWith("https://apk.example/dl/313", "_blank", "noopener");
    open.mockRestore();
  });

  // No APK assets to read muma-mobile's CHANGELOG.md from -- null is what keeps
  // mobileReleaseNotes.js's once-per-upgrade modal from ever showing here.
  it("has no release notes of its own to report", async () => {
    await expect(browserSystem.releaseNotes()).resolves.toBeNull();
  });

  // The web resolves both bases in store.js, from window.location; this only
  // reads them back, so a change there cannot be undone here.
  it("reads the bases the web already resolved", () => {
    credentials.set({ url: "https://lms.example", username: "demo-user", password: "pw" });
    mumaApiUrl.set("/muma");

    expect(browserSystem.serverUrl()).toEqual({
      subsonic: "https://lms.example",
      mumaApi: "/muma",
      configured: true,
    });
  });

  // Issue #192: the first-run screen is the shell's; a browser tab never needs it.
  it("has no server address of its own to check, store or suggest", async () => {
    await expect(
      browserSystem.checkServerAddress("https://music.example.net"),
    ).resolves.toMatchObject({
      state: "ok",
    });
    await expect(
      browserSystem.setServerAddress({ url: "https://music.example.net", signOut: false }),
    ).rejects.toMatchObject({ code: "invalid" });
    await expect(browserSystem.suggestedServerAddress()).resolves.toBe("");
  });

  it("has no platform events, but every subscription can be undone", () => {
    const handler = vi.fn();

    browserSystem.onBack(handler)();
    browserSystem.onDeepLink(handler)();
    browserSystem.carConnected(handler)();

    expect(handler).not.toHaveBeenCalled();
  });

  // A browser tab is never in a car; this is the same honest-empty answer carConnected
  // gives by never firing, just readable once instead of waited for.
  it("carState is never connected", async () => {
    await expect(browserSystem.carState()).resolves.toEqual({ connected: false });
  });

  // There is no lock screen to ask in a browser tab.
  it("setKeepScreenOn is a no-op that resolves", async () => {
    await expect(
      browserSystem.setKeepScreenOn({ showWhenLocked: true, turnScreenOn: true }),
    ).resolves.toBeUndefined();
  });

  // The PC's floating window is its own document, so the tab itself is always full.
  it("is always a full window that cannot open Maps next to itself", async () => {
    const handler = vi.fn();

    await expect(browserSystem.windowMode()).resolves.toEqual({ mode: "full" });
    browserSystem.onWindowModeChanged(handler)();
    await expect(browserSystem.canNavigate()).resolves.toEqual({ value: false });
    await expect(browserSystem.navigateAdjacent()).resolves.toBeUndefined();
    expect(handler).not.toHaveBeenCalled();
  });

  // A browser tab has no native session and nowhere to persist one; both resolve at
  // once rather than making every caller branch on `isNative` first.
  it("signOut and saveCredentials are no-ops that resolve", async () => {
    await expect(browserSystem.signOut()).resolves.toBeUndefined();
    await expect(
      browserSystem.saveCredentials({
        url: "https://lms.example",
        username: "demo-user",
        password: "pw",
      }),
    ).resolves.toBeUndefined();
  });

  // The device-settings tab never shows without isNative, so these are never actually
  // read in a browser tab; they still have to resolve rather than throw.
  it("getSettings and setSetting are no-ops that resolve", async () => {
    await expect(browserSystem.getSettings()).resolves.toEqual({});
    await expect(
      browserSystem.setSetting({ key: "wifiOnly", value: true }),
    ).resolves.toBeUndefined();
  });

  // Technical criterion 9 of phone-ui-polish: null is what hides the output label in a tab.
  it("has no audio output to name, no route events, and no picker to open", async () => {
    await expect(browserSystem.outputRoute()).resolves.toBeNull();
    const handler = vi.fn();
    browserSystem.onOutputRouteChanged(handler)();
    expect(handler).not.toHaveBeenCalled();
    await expect(browserSystem.openOutputPicker()).resolves.toBeUndefined();
  });
});
