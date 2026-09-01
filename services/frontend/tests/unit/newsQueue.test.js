import { describe, it, expect } from "vitest";
import { snapshotOf, restoreTarget, bulletinStreamUrl } from "../../src/lib/newsQueue.js";

describe("newsQueue", () => {
  it("remembers the track and position it interrupted", () => {
    const snapshot = snapshotOf({ trackId: "42", positionSeconds: 87.5, radioChannel: null });
    expect(restoreTarget(snapshot)).toEqual({
      action: "track",
      trackId: "42",
      positionSeconds: 87.5,
    });
  });

  it("re-tunes radio instead of restoring a stale position", () => {
    const snapshot = snapshotOf({ trackId: null, positionSeconds: 12, radioChannel: "main" });
    expect(restoreTarget(snapshot)).toEqual({ action: "retune", channel: "main" });
  });

  it("lets radio win when a track is still loaded behind it", () => {
    const snapshot = snapshotOf({ trackId: "42", positionSeconds: 12, radioChannel: "main" });
    expect(restoreTarget(snapshot)).toEqual({ action: "retune", channel: "main" });
  });

  it("has nothing to restore when the player was idle", () => {
    expect(snapshotOf({ trackId: null, positionSeconds: 0, radioChannel: null })).toBeNull();
    expect(restoreTarget(null)).toEqual({ action: "none" });
  });

  it("builds the stream url", () => {
    expect(bulletinStreamUrl("https://muma.test", 7)).toBe(
      "https://muma.test/api/news/bulletins/7/stream",
    );
  });
});
