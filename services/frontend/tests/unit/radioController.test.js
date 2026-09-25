import { describe, it, expect, beforeEach, vi } from "vitest";
import { createRadioController } from "../../src/lib/radioController";

function makeAudio() {
  return {
    src: "",
    currentTime: 0,
    paused: true,
    playbackRate: 1,
    play: vi.fn(() => Promise.resolve()),
    pause: vi.fn(),
  };
}

function stateResponse(overrides = {}) {
  return {
    server_time: 1000,
    channel: { slug: "main", name: "Radio", genre: null },
    current: {
      track_id: "tr-42",
      title: "T",
      artist: "A",
      album: "B",
      cover_art: "al-7",
      duration_ms: 215000,
      started_at: 970,
      ends_at: 1185,
    },
    next: null,
    ...overrides,
  };
}

describe("createRadioController", () => {
  let audio;
  let fetchImpl;
  let clock;

  beforeEach(() => {
    audio = makeAudio();
    clock = 1_000_000;
    fetchImpl = vi.fn((url) => {
      if (url.includes("/time")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ server_time: 1000 }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(stateResponse()) });
    });
  });

  function make(overrides = {}) {
    return createRadioController({
      audio,
      apiBase: "/muma",
      apiKey: "k",
      streamUrlFor: (id, offset) => `/rest/stream?id=${id}&timeOffset=${offset}`,
      fetchImpl,
      now: () => clock,
      sampleCount: 1,
      ...overrides,
    });
  }

  it("starts the current track at the server position", async () => {
    const controller = make();
    await controller.start("main");
    // server_time 1000, entry started_at 970 => 30s in.
    expect(audio.src).toBe("/rest/stream?id=tr-42&timeOffset=30");
    expect(audio.play).toHaveBeenCalled();
  });

  it("exposes the current entry as now-playing metadata", async () => {
    const controller = make();
    await controller.start("main");
    expect(controller.getEntry().track_id).toBe("tr-42");
  });

  it("sends the api key with every call", async () => {
    const controller = make();
    await controller.start("main");
    expect(fetchImpl.mock.calls[0][1].headers["X-API-Key"]).toBe("k");
  });

  it("nudges playbackRate for a small drift instead of reloading", async () => {
    const controller = make();
    await controller.start("main");
    audio.src = "unchanged";
    audio.currentTime = 1; // true position 31, target still ~30 => 1s ahead
    controller.tick();
    expect(audio.playbackRate).toBeLessThan(1);
    expect(audio.src).toBe("unchanged");
  });

  it("reloads the stream at the new offset for a large drift", async () => {
    const controller = make();
    await controller.start("main");
    audio.currentTime = 120; // true position 150, target ~30 => way ahead
    controller.tick();
    expect(audio.src).toBe("/rest/stream?id=tr-42&timeOffset=30");
  });

  it("switches to the next entry when the current one has ended", async () => {
    const controller = make();
    await controller.start("main");
    // 200s of wall-clock later; the measured offset stays valid.
    clock += 200_000;
    fetchImpl.mockImplementation((url) => {
      if (url.includes("/time")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ server_time: 1200 }) });
      }
      return Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve(
            stateResponse({
              server_time: 1200,
              current: {
                track_id: "tr-43",
                title: "N",
                artist: "A",
                album: "B",
                cover_art: null,
                duration_ms: 180000,
                started_at: 1185,
                ends_at: 1365,
              },
            }),
          ),
      });
    });
    await controller.refresh();
    expect(controller.getEntry().track_id).toBe("tr-43");
    expect(audio.src).toBe("/rest/stream?id=tr-43&timeOffset=15");
  });

  it("re-measures the clock offset on demand", async () => {
    const controller = make();
    await controller.start("main");
    const callsBefore = fetchImpl.mock.calls.filter((c) => c[0].includes("/time")).length;
    await controller.measureClockOffset();
    const callsAfter = fetchImpl.mock.calls.filter((c) => c[0].includes("/time")).length;
    expect(callsAfter).toBeGreaterThan(callsBefore);
  });

  it("pauses and clears state on stop", async () => {
    const controller = make();
    await controller.start("main");
    controller.stop();
    expect(audio.pause).toHaveBeenCalled();
    expect(audio.playbackRate).toBe(1);
    expect(controller.getEntry()).toBeNull();
  });

  it("does nothing on tick when not started", () => {
    const controller = make();
    expect(() => controller.tick()).not.toThrow();
  });

  // Native: the platform service streams the channel and corrects its own drift
  // (see RadioPlaybackController.kt); this instance only exists there for
  // `getEntry()`, so every place that would touch the element has to be a
  // no-op rather than a crash on a null `audio`.
  it("still tracks the entry for display when there is no audio element to drive", async () => {
    const controller = make({ audio: null });
    await controller.start("main");
    expect(controller.getEntry().track_id).toBe("tr-42");
    expect(() => controller.tick()).not.toThrow();
    expect(() => controller.stop()).not.toThrow();
  });

  it("survives a channel with an empty timeline", async () => {
    fetchImpl = vi.fn((url) => {
      if (url.includes("/time")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ server_time: 1000 }) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(stateResponse({ current: null })),
      });
    });
    const controller = make({ fetchImpl });
    await controller.start("main");
    expect(controller.getEntry()).toBeNull();
    expect(audio.play).not.toHaveBeenCalled();
  });

  // A controller superseded mid-start (a channel switch, radio switched off) used to finish its
  // first state fetch anyway and load its stream over the newer one.
  it("a retired controller never loads the stream its in-flight start was fetching", async () => {
    let releaseState;
    fetchImpl = vi.fn((url) => {
      if (url.includes("/time")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ server_time: 1000 }) });
      }
      return new Promise((resolve) => {
        releaseState = () => resolve({ ok: true, json: () => Promise.resolve(stateResponse()) });
      });
    });
    const controller = make();

    const started = controller.start("main");
    await vi.waitFor(() => expect(releaseState).toBeTypeOf("function"));
    controller.retire();
    releaseState();
    await started;

    expect(audio.src).toBe("");
    expect(audio.play).not.toHaveBeenCalled();
    expect(audio.pause).not.toHaveBeenCalled();
    expect(controller.getEntry()).toBeNull();
  });

  it("a stop during the clock measurement skips the first state fetch", async () => {
    let releaseTime;
    fetchImpl = vi.fn((url) => {
      if (url.includes("/time")) {
        return new Promise((resolve) => {
          releaseTime = () =>
            resolve({ ok: true, json: () => Promise.resolve({ server_time: 1000 }) });
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(stateResponse()) });
    });
    const controller = make();

    const started = controller.start("main");
    await vi.waitFor(() => expect(releaseTime).toBeTypeOf("function"));
    controller.stop();
    releaseTime();
    await started;

    expect(fetchImpl.mock.calls.some(([url]) => url.includes("/state"))).toBe(false);
    expect(audio.src).toBe("");
  });
});
