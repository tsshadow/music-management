import { describe, it, expect, beforeEach, vi } from "vitest";
import { createCapacitorPlatform } from "../../src/lib/platform/capacitor/index.js";

/**
 * The Android shell's half of the platform contract.
 *
 * There is no bridge here, so every plugin is a fake: it records the calls it
 * was made with and hands the test a way to fire the events the Kotlin side
 * would have sent. That is the only thing worth testing at this level -- the
 * proxies own no logic beyond shaping arguments and defending against a
 * malformed message from another process, and both of those are exactly what a
 * contract between two codebases gets wrong.
 */

/** A plugin that records calls and lets the test fire its listeners. */
function fakePlugin(answers = {}) {
  const listeners = new Map();
  const calls = [];

  const plugin = new Proxy(
    {
      addListener(event, handler) {
        if (!listeners.has(event)) listeners.set(event, new Set());
        listeners.get(event).add(handler);
        return Promise.resolve({
          remove: () => listeners.get(event).delete(handler),
        });
      },
      /** Fires one event at everything subscribed to it. */
      emit(event, payload) {
        for (const handler of listeners.get(event) ?? []) handler(payload);
      },
      calls,
      listenerCount: (event) => listeners.get(event)?.size ?? 0,
    },
    {
      get(target, property) {
        if (property in target) return target[property];
        return (argument) => {
          calls.push([property, argument]);
          const answer = answers[property];
          return Promise.resolve(typeof answer === "function" ? answer(argument) : answer);
        };
      },
    },
  );
  return plugin;
}

/** Builds a platform out of fakes, keyed by the plugin name. */
function nativePlatform(answersByPlugin = {}) {
  const plugins = {};
  const platform = createCapacitorPlatform((name) => {
    plugins[name] = fakePlugin(answersByPlugin[name] ?? {});
    return plugins[name];
  });
  return { platform, plugins };
}

const PLAYING = {
  status: "playing",
  position: 12.5,
  duration: 200,
  trackId: "42",
  volume: 0.8,
  queueIndex: 1,
  queueLength: 3,
  shuffle: false,
  repeat: "none",
};

describe("capacitor platform", () => {
  it("registers exactly the five plugin names the Kotlin side annotates", () => {
    const names = [];
    createCapacitorPlatform((name) => {
      names.push(name);
      return fakePlugin();
    });

    expect(names.sort()).toEqual([
      "MumaDiagnostics",
      "MumaPlayer",
      "MumaSpeech",
      "MumaStorage",
      "MumaSystem",
    ]);
  });

  it("is the five members the UI is allowed to know about", () => {
    const { platform } = nativePlatform();

    expect(Object.keys(platform).sort()).toEqual([
      "diagnostics",
      "player",
      "speech",
      "storage",
      "system",
    ]);
  });
});

describe("capacitor player", () => {
  let platform;
  let plugins;

  beforeEach(() => {
    ({ platform, plugins } = nativePlatform({
      MumaPlayer: {
        state: PLAYING,
        queueState: { index: 1, length: 3, trackIds: [1, 42, 7] },
        setQueue: { index: 1, length: 3, trackIds: [1, 42, 7] },
      },
    }));
  });

  it("says the queue is not the UI's", () => {
    expect(platform.player.ownsQueue).toBe(true);
  });

  // Acceptance criterion 2 of the design: no second engine, ever.
  it("has no media element and nothing to attach one to", () => {
    expect(platform.player.element()).toBe(null);
    expect(() => platform.player.attach(document.createElement("audio"))).not.toThrow();
    expect(platform.player.ready()).toBe(true);
  });

  it("answers state() synchronously from the last thing the service said", () => {
    expect(platform.player.state().status).toBe("idle");

    plugins.MumaPlayer.emit("timeupdate", PLAYING);

    expect(platform.player.state()).toEqual(PLAYING);
  });

  it("pulls a snapshot on demand, which is what a rebuilt WebView does first", async () => {
    expect(await platform.player.refresh()).toEqual(PLAYING);
    expect(platform.player.state().position).toBe(12.5);
  });

  it("keeps the last known position when a message leaves it out", () => {
    plugins.MumaPlayer.emit("timeupdate", PLAYING);
    plugins.MumaPlayer.emit("pause", { status: "paused", trackId: "42" });

    expect(platform.player.state().position).toBe(12.5);
    expect(platform.player.state().status).toBe("paused");
  });

  it("hands every event the snapshot it left behind", () => {
    const seen = [];
    platform.player.on("play", (state) => seen.push(state));

    plugins.MumaPlayer.emit("play", PLAYING);

    expect(seen).toEqual([PLAYING]);
  });

  it("carries the reason on an error and nothing extra on the rest", () => {
    const errors = [];
    platform.player.on("error", (state) => errors.push(state));

    plugins.MumaPlayer.emit("error", { ...PLAYING, status: "error", code: 2, message: "gone" });

    expect(errors[0].code).toBe(2);
    expect(errors[0].message).toBe("gone");
  });

  it("reports a transport move the service already performed", () => {
    const commands = [];
    platform.player.on("command", (command) => commands.push(command));

    plugins.MumaPlayer.emit("timeupdate", PLAYING);
    plugins.MumaPlayer.emit("command", { name: "next" });
    plugins.MumaPlayer.emit("command", { name: "seekTo", seconds: 90 });

    expect(commands.map((c) => c.name)).toEqual(["next", "seekTo"]);
    expect(commands[0].state.trackId).toBe("42");
    expect(commands[1].seconds).toBe(90);
  });

  it("unsubscribes", () => {
    const handler = vi.fn();
    platform.player.on("play", handler)();

    plugins.MumaPlayer.emit("play", PLAYING);

    expect(handler).not.toHaveBeenCalled();
  });

  it("refuses an event name that is not in the contract", () => {
    expect(() => platform.player.on("progress", () => {})).toThrow(/Unknown player event/);
  });

  // The plugin rejects a load without one, so a caller that only has a URL --
  // which is every browser call site -- must not reach the bridge at all.
  it("never loads without a track id", async () => {
    await platform.player.load({ url: "https://lms.example/rest/stream?id=42" });

    expect(plugins.MumaPlayer.calls).toEqual([]);
  });

  it("loads by id and lets the service resolve the source", async () => {
    await platform.player.load({ url: "ignored", trackId: 42, position: 30, autoplay: true });

    expect(plugins.MumaPlayer.calls).toEqual([
      ["load", { trackId: "42", position: 30, autoplay: true }],
    ]);
  });

  it("hands the whole queue across and reads it back", async () => {
    const tracks = [{ id: "1", title: "One" }];

    expect(await platform.player.setQueue({ tracks, index: 0, autoplay: false })).toEqual({
      index: 1,
      length: 3,
      trackIds: ["1", "42", "7"],
    });
    expect(await platform.player.queueState()).toEqual({
      index: 1,
      length: 3,
      trackIds: ["1", "42", "7"],
    });
  });

  it("reads an unreachable queue as an empty one rather than throwing", async () => {
    const { platform: broken } = nativePlatform({
      MumaPlayer: {
        queueState: () => {
          throw new Error("no service");
        },
      },
    });

    expect(await broken.player.queueState()).toEqual({ index: -1, length: 0, trackIds: [] });
  });

  it("clamps the volume the way the browser engine does", () => {
    platform.player.setVolume(4);
    platform.player.setVolume(-1);

    expect(plugins.MumaPlayer.calls).toEqual([
      ["setVolume", { value: 1 }],
      ["setVolume", { value: 0 }],
    ]);
  });

  it("passes seconds to seek, not milliseconds", () => {
    platform.player.seek(42);

    expect(plugins.MumaPlayer.calls).toEqual([["seek", { seconds: 42 }]]);
  });

  it("sends the equalizer curve and answers with what the platform said", async () => {
    const { platform: native, plugins: fakes } = nativePlatform({
      MumaPlayer: { setEqualizer: { value: true } },
    });

    expect(native.player.setEqualizer({ enabled: true, gains: [1, 2], preamp: 3 })).toBe(false);
    await Promise.resolve();
    expect(fakes.MumaPlayer.calls).toEqual([
      ["setEqualizer", { enabled: true, gains: [1, 2], preamp: 3 }],
    ]);
    expect(native.player.setEqualizer({ enabled: true, gains: [], preamp: 0 })).toBe(true);
  });

  // The MediaSession already draws the notification from the queue it was
  // handed; a second source of truth is the bug this design avoids.
  it("takes transport handlers and wires none of them", () => {
    expect(() => platform.player.setCommandHandlers({ next: () => {} })).not.toThrow();
    expect(plugins.MumaPlayer.calls).toEqual([]);
  });

  // Shuffle and repeat live on the service once it owns the queue -- Media3
  // applies both by itself, with no JS in the loop -- so `setMode` sends the
  // ask and trusts the answer over it, the same shape every other event does.
  it("asks the service for a mode and mirrors what it actually applied", async () => {
    const { platform: native, plugins: fakes } = nativePlatform({
      MumaPlayer: { setMode: { ...PLAYING, shuffle: true, repeat: "one" } },
    });

    const answer = await native.player.setMode({ shuffle: true, repeat: "all" });

    expect(fakes.MumaPlayer.calls).toEqual([["setMode", { shuffle: true, repeat: "all" }]]);
    // The service answered "one", not the "all" that was asked for.
    expect(answer).toMatchObject({ shuffle: true, repeat: "one" });
    expect(native.player.state()).toMatchObject({ shuffle: true, repeat: "one" });
  });

  it("defaults a mode call made without one to off", async () => {
    await platform.player.setMode();

    expect(plugins.MumaPlayer.calls).toEqual([["setMode", { shuffle: false, repeat: "none" }]]);
  });

  // Android Auto's own repeat button, or the notification, can move the
  // service without the WebView ever calling `setMode`; every event still
  // carries the fields, the same as every other part of the snapshot.
  it("picks up a mode changed from outside the WebView on any event", () => {
    plugins.MumaPlayer.emit("timeupdate", { ...PLAYING, shuffle: true, repeat: "all" });

    expect(platform.player.state()).toMatchObject({ shuffle: true, repeat: "all" });
  });

  it("keeps the last known mode when a message leaves it out", () => {
    plugins.MumaPlayer.emit("play", { ...PLAYING, shuffle: true, repeat: "one" });
    plugins.MumaPlayer.emit("pause", { status: "paused", trackId: "42" });

    expect(platform.player.state()).toMatchObject({ shuffle: true, repeat: "one" });
  });

  it("refuses a repeat word the contract does not know, rather than trust the far side blindly", () => {
    plugins.MumaPlayer.emit("play", { ...PLAYING, shuffle: true, repeat: "one" });
    plugins.MumaPlayer.emit("pause", { repeat: "backwards" });

    expect(platform.player.state().repeat).toBe("one");
  });
});

describe("capacitor system", () => {
  it("is a native shell", () => {
    const { platform } = nativePlatform();

    expect(platform.system.isNative).toBe(true);
  });

  it("answers serverUrl synchronously, from what the boot path loaded", async () => {
    const { platform } = nativePlatform({
      MumaSystem: {
        serverUrl: { subsonic: "https://lms.example/", mumaApi: "https://lms.example/muma" },
      },
    });

    expect(platform.system.serverUrl()).toEqual({ subsonic: "", mumaApi: "" });

    await platform.system.loadServerUrl();

    // Trailing slash gone: a path starting with one would otherwise double it.
    expect(platform.system.serverUrl()).toEqual({
      subsonic: "https://lms.example",
      mumaApi: "https://lms.example/muma",
    });
  });

  it("reads the phone's credentials, blank password and all", async () => {
    const { platform } = nativePlatform({
      MumaSystem: { credentials: { username: "user", password: "", clientId: "Ultrasonic" } },
    });

    expect(await platform.system.credentials()).toEqual({
      username: "user",
      password: "",
      clientId: "Ultrasonic",
      forcePlainTextPassword: false,
      serverId: 0,
      mumaApiKey: "",
      mumaUserId: 0,
    });
  });

  // The activity finishes 350 ms after emitting `back`, so the claim cannot be
  // behind an await -- and a press the UI did not use must not be claimed.
  it("claims a back press in the same turn, and only when it was used", () => {
    const { platform, plugins } = nativePlatform();
    let used = true;
    platform.system.onBack(() => used);

    plugins.MumaSystem.emit("back", { seq: 7 });

    expect(plugins.MumaSystem.calls).toEqual([["handledBack", { seq: 7 }]]);

    used = false;
    plugins.MumaSystem.emit("back", { seq: 8 });

    expect(plugins.MumaSystem.calls).toHaveLength(1);
  });

  it("lets the shell close when the back handler throws", () => {
    const { platform, plugins } = nativePlatform();
    platform.system.onBack(() => {
      throw new Error("a screen blew up");
    });

    expect(() => plugins.MumaSystem.emit("back", { seq: 1 })).not.toThrow();
    expect(plugins.MumaSystem.calls).toEqual([]);
  });

  it("passes a deep link route through and ignores an empty one", () => {
    const { platform, plugins } = nativePlatform();
    const routes = [];
    platform.system.onDeepLink((route) => routes.push(route));

    plugins.MumaSystem.emit("deepLink", { route: "search:hardstyle" });
    plugins.MumaSystem.emit("deepLink", {});

    expect(routes).toEqual(["search:hardstyle"]);
  });

  it("reports car presence as a boolean", () => {
    const { platform, plugins } = nativePlatform();
    const seen = [];
    platform.system.carConnected((connected) => seen.push(connected));

    plugins.MumaSystem.emit("carConnected", { connected: true });
    plugins.MumaSystem.emit("carConnected", {});

    expect(seen).toEqual([true, false]);
  });

  it("hands the phone back to the Kotlin interface", () => {
    const { platform, plugins } = nativePlatform();

    platform.system.switchToLegacyUi();
    platform.system.openLegacySettings();

    expect(plugins.MumaSystem.calls.map(([name]) => name)).toEqual([
      "switchToLegacyUi",
      "openLegacySettings",
    ]);
  });

  it("forwards signOut to the plugin and awaits it", async () => {
    const { platform, plugins } = nativePlatform();

    await platform.system.signOut();

    expect(plugins.MumaSystem.calls).toEqual([["signOut", undefined]]);
  });

  it("forwards a verified pair to saveCredentials unchanged", async () => {
    const { platform, plugins } = nativePlatform();
    const creds = { url: "https://lms.example", username: "user", password: "hunter2" };

    await platform.system.saveCredentials(creds);

    expect(plugins.MumaSystem.calls).toEqual([["saveCredentials", creds]]);
  });

  it("answers the device-settings tab's whole state from the plugin", async () => {
    const { platform } = nativePlatform({
      MumaSystem: { getSettings: { wifiOnly: true, parallelDownloads: 3 } },
    });

    expect(await platform.system.getSettings()).toEqual({ wifiOnly: true, parallelDownloads: 3 });
  });

  it("forwards a setting write unchanged and awaits it", async () => {
    const { platform, plugins } = nativePlatform();

    await platform.system.setSetting({ key: "wifiOnly", value: true });

    expect(plugins.MumaSystem.calls).toEqual([["setSetting", { key: "wifiOnly", value: true }]]);
  });
});

describe("capacitor storage", () => {
  it("can keep music, which is what shows the downloads screen", () => {
    const { platform } = nativePlatform();

    expect(platform.storage.supported).toBe(true);
  });

  it("batches one id into the list the plugin wants", async () => {
    const { platform, plugins } = nativePlatform({
      MumaStorage: { download: { requested: 1, unknown: 0 }, remove: { removed: 1 } },
    });

    await platform.storage.download("42", { pin: true });
    await platform.storage.remove(["1", "2"]);

    expect(plugins.MumaStorage.calls).toEqual([
      ["download", { ids: ["42"], pin: true }],
      ["remove", { ids: ["1", "2"] }],
    ]);
  });

  it("answers for every id it was asked about, even the ones the phone skipped", async () => {
    const { platform } = nativePlatform({ MumaStorage: { stateOf: { a: "done" } } });

    expect(await platform.storage.stateOf(["a", "b"])).toEqual({ a: "done", b: "none" });
  });

  it("asks nothing for an empty list", async () => {
    const { platform, plugins } = nativePlatform();

    expect(await platform.storage.stateOf([])).toEqual({});
    expect(plugins.MumaStorage.calls).toEqual([]);
  });

  it("unwraps the plugin's single-value answers", async () => {
    const { platform } = nativePlatform({
      MumaStorage: {
        isLocal: { value: true },
        size: { value: 4096 },
        list: { items: [{ id: "1" }] },
      },
    });

    expect(await platform.storage.isLocal("1")).toBe(true);
    expect(await platform.storage.size()).toBe(4096);
    expect(await platform.storage.list()).toEqual([{ id: "1" }]);
  });

  it("forwards clearCache to the plugin and awaits it", async () => {
    const { platform, plugins } = nativePlatform();

    await platform.storage.clearCache();

    expect(plugins.MumaStorage.calls).toEqual([["clearCache", undefined]]);
  });

  it("reports download progress per id", () => {
    const { platform, plugins } = nativePlatform();
    const seen = [];
    platform.storage.onProgress((event) => seen.push(event));

    plugins.MumaStorage.emit("progress", { id: 5, state: "running", progress: 40 });

    expect(seen).toEqual([{ id: "5", state: "running", progress: 40 }]);
  });
});

describe("capacitor speech", () => {
  it("assumes a phone can listen until told otherwise", async () => {
    const { platform } = nativePlatform({ MumaSpeech: { supported: { value: false } } });

    expect(platform.speech.supported).toBe(true);
    expect(await platform.speech.loadSupported()).toBe(false);
    expect(platform.speech.supported).toBe(false);
  });

  it("passes every reading the recogniser offered, best first", () => {
    const { platform, plugins } = nativePlatform();
    const finals = [];
    platform.speech.onFinal((event) => finals.push(event));

    plugins.MumaSpeech.emit("final", {
      text: "speel hardstyle",
      alternatives: [{ text: "speel hardstyle", confidence: 0.9 }],
    });

    expect(finals[0].text).toBe("speel hardstyle");
    expect(finals[0].alternatives).toHaveLength(1);
  });

  it("reports a recogniser error as a code", () => {
    const { platform, plugins } = nativePlatform();
    const codes = [];
    platform.speech.onError((event) => codes.push(event.code));

    plugins.MumaSpeech.emit("error", { code: 9 });

    expect(codes).toEqual([9]);
  });
});

describe("capacitor diagnostics", () => {
  it("keeps a readable copy here and sends the same line across", () => {
    const { platform, plugins } = nativePlatform();

    platform.diagnostics.log("navigate", { view: "albums" });

    expect(platform.diagnostics.report().map((entry) => entry.action)).toEqual(["navigate"]);
    expect(plugins.MumaDiagnostics.calls).toEqual([
      ["log", { action: "navigate", detail: { view: "albums" } }],
    ]);
  });

  it("reads the whole trail, the native app's actions included", async () => {
    const { platform } = nativePlatform({
      MumaDiagnostics: { report: { entries: [{ action: "car:connected", at: 1, detail: null }] } },
    });

    expect(await platform.diagnostics.nativeReport()).toEqual([
      { action: "car:connected", at: 1, detail: null },
    ]);
  });

  it("empties both buffers", () => {
    const { platform, plugins } = nativePlatform();
    platform.diagnostics.log("play");

    platform.diagnostics.clear();

    expect(platform.diagnostics.report()).toEqual([]);
    expect(plugins.MumaDiagnostics.calls.map(([name]) => name)).toEqual(["log", "clear"]);
  });

  it("sends the bundle version and user agent across the bridge", () => {
    const { platform, plugins } = nativePlatform();

    platform.diagnostics.identify({ bundleVersion: "abc1234", userAgent: "Mozilla/5.0" });

    expect(plugins.MumaDiagnostics.calls).toEqual([
      ["identify", { bundleVersion: "abc1234", userAgent: "Mozilla/5.0" }],
    ]);
  });

  it("identifies with nulls rather than undefined when nothing is known", () => {
    const { platform, plugins } = nativePlatform();

    platform.diagnostics.identify({});

    expect(plugins.MumaDiagnostics.calls).toEqual([
      ["identify", { bundleVersion: null, userAgent: null }],
    ]);
  });
});
