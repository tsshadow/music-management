import { describe, it, expect, vi, afterEach } from "vitest";
import {
  SHARE_HEIGHT,
  SHARE_WIDTH,
  drawShareCard,
  renderShareCard,
  shareFileName,
  wrapLines,
} from "../../src/lib/wrapped/shareCard.js";
import browserSystem from "../../src/lib/platform/browser/system.js";
import { createCapacitorSystem } from "../../src/lib/platform/capacitor/system.js";

/** A 2D context that records every text it is asked to draw; each character is 20 px wide. */
function recordingContext() {
  const texts = [];
  return {
    texts,
    fillRect: vi.fn(),
    fillText: (text) => texts.push(String(text)),
    measureText: (text) => ({ width: String(text).length * 20 }),
    createLinearGradient: () => ({ addColorStop: vi.fn() }),
  };
}

const FACE = {
  id: "top_artists",
  label: "Top artists",
  headline: "Artist A",
  sentence: "300 listens.",
  notes: [],
  items: [
    { label: "Artist A", value: "300" },
    { label: "Artist B", value: "200" },
  ],
};

describe("shareCard", () => {
  it("draws the face, the period and the brand, and nothing about the account", () => {
    const ctx = recordingContext();
    drawShareCard(ctx, FACE, { period: "2026", brand: "MuMa Wrapped", tint: "#aa0000" });
    const all = ctx.texts.join("\n");
    expect(all).toContain("TOP ARTISTS");
    expect(all).toContain("Artist A");
    expect(all).toContain("300 listens.");
    expect(all).toContain("2 Artist B");
    expect(all).toContain("MuMa Wrapped");
    expect(all).toContain("2026");
    // The face and the period are the only inputs; a username cannot reach the image.
    expect(all).not.toMatch(/alice|https?:/);
  });

  it("draws the bars of a bars card and fills the panel without a tint", () => {
    const ctx = recordingContext();
    const bars = { ...FACE, items: undefined, bars: [{ label: "Tracks", text: "800" }] };
    drawShareCard(ctx, bars, { period: "2026", brand: "MuMa Wrapped" });
    expect(ctx.texts).toContain("Tracks");
    expect(ctx.texts).toContain("800");
    expect(ctx.fillStyle).toBeDefined();
  });

  it("wraps text at the width and keeps a long word whole", () => {
    const ctx = recordingContext();
    expect(wrapLines(ctx, "aa bb cc", 100)).toEqual(["aa bb", "cc"]);
    expect(wrapLines(ctx, "abcdefghijkl", 100)).toEqual(["abcdefghijkl"]);
    expect(wrapLines(ctx, null, 100)).toEqual([]);
  });

  it("renders a 1080 by 1920 PNG", () => {
    const ctx = recordingContext();
    const canvas = { getContext: () => ctx, toDataURL: vi.fn(() => "data:image/png;base64,X") };
    expect(renderShareCard(FACE, { period: "2026", brand: "MuMa Wrapped" }, () => canvas)).toBe(
      "data:image/png;base64,X",
    );
    expect(canvas.width).toBe(SHARE_WIDTH);
    expect(canvas.height).toBe(SHARE_HEIGHT);
    expect(canvas.toDataURL).toHaveBeenCalledWith("image/png");
    const blind = { getContext: () => null };
    expect(() => renderShareCard(FACE, {}, () => blind)).toThrow(/canvas/);
  });

  it("names the file after the period and the card", () => {
    expect(shareFileName("2026-03-01_2026-06-30", "top_artists")).toBe(
      "muma-wrapped-2026-03-01-2026-06-30-top-artists.png",
    );
  });
});

describe("platform share", () => {
  const originalShare = navigator.share;
  const originalCanShare = navigator.canShare;

  afterEach(() => {
    navigator.share = originalShare;
    navigator.canShare = originalCanShare;
    vi.restoreAllMocks();
  });

  const IMAGE = {
    dataUrl: "data:image/png;base64,AAAA",
    title: "MuMa Wrapped 2026",
    fileName: "w.png",
  };

  function stubFetch() {
    globalThis.fetch = vi.fn(async () => ({
      blob: async () => new Blob(["x"], { type: "image/png" }),
    }));
  }

  it("uses the Web Share API with a file when the browser can share files", async () => {
    stubFetch();
    navigator.canShare = vi.fn(() => true);
    navigator.share = vi.fn(async () => {});
    expect(await browserSystem.share(IMAGE)).toBe("shared");
    const [data] = navigator.share.mock.calls[0];
    expect(data.files[0].name).toBe("w.png");
    expect(data.title).toBe("MuMa Wrapped 2026");
  });

  it("reports a share the listener cancelled", async () => {
    stubFetch();
    navigator.canShare = () => true;
    navigator.share = vi.fn(async () =>
      Promise.reject(Object.assign(new Error("x"), { name: "AbortError" })),
    );
    expect(await browserSystem.share(IMAGE)).toBe("cancelled");
  });

  it("downloads the image when the browser cannot share files", async () => {
    navigator.share = undefined;
    navigator.canShare = undefined;
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    expect(await browserSystem.share(IMAGE)).toBe("saved");
    expect(click).toHaveBeenCalledOnce();
  });

  it("falls back to a download when sharing is refused", async () => {
    stubFetch();
    navigator.canShare = () => true;
    navigator.share = vi.fn(async () => Promise.reject(new Error("NotAllowedError")));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    expect(await browserSystem.share(IMAGE)).toBe("saved");
  });

  it("hands the image to the shell's share sheet", async () => {
    const plugin = { share: vi.fn(async () => ({})) };
    expect(await createCapacitorSystem(plugin).share(IMAGE)).toBe("shared");
    expect(plugin.share).toHaveBeenCalledWith(IMAGE);
  });
});
