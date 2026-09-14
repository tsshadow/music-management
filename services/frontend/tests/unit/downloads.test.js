import { describe, it, expect } from "vitest";
import {
  ASSUMED_BITRATE_KBPS,
  SET_SECONDS,
  formatBytes,
  groupDownloads,
  groupProgress,
  groupState,
  isSet,
  trackSize,
} from "../../src/lib/downloads.js";

describe("trackSize", () => {
  it("uses the figure the library reported", () => {
    expect(trackSize({ size: 8_400_000, duration: 210, bitRate: 320 })).toEqual({
      bytes: 8_400_000,
      estimated: false,
    });
  });

  it("estimates from the reported bitrate when there is no size", () => {
    expect(trackSize({ duration: 60, bitRate: 128 })).toEqual({
      bytes: 960_000,
      estimated: true,
    });
  });

  // 320 rather than an average: an estimate that is too low is the one that
  // hurts, because it is the one that fills a phone.
  it("assumes the top bitrate when the library reported neither", () => {
    const { bytes, estimated } = trackSize({ duration: 60 });

    expect(bytes).toBe((ASSUMED_BITRATE_KBPS * 1000 * 60) / 8);
    expect(estimated).toBe(true);
  });

  it("is zero when there is nothing to guess from", () => {
    expect(trackSize({}).bytes).toBe(0);
    expect(trackSize(undefined).bytes).toBe(0);
  });
});

describe("isSet", () => {
  it("is the ten-minute boundary, inclusive, that the rest of the app uses", () => {
    expect(isSet({ duration: SET_SECONDS })).toBe(true);
    expect(isSet({ duration: SET_SECONDS - 1 })).toBe(false);
    expect(isSet({})).toBe(false);
  });
});

describe("formatBytes", () => {
  it("counts in the decimal units Android's own storage screen uses", () => {
    expect(formatBytes(0, "en")).toBe("0 MB");
    expect(formatBytes(999, "en")).toBe("999 B");
    expect(formatBytes(1000, "en")).toBe("1 kB");
    expect(formatBytes(8_400_000, "en")).toBe("8.4 MB");
    expect(formatBytes(1_240_000_000, "en")).toBe("1.2 GB");
  });

  it("does not pretend to a decimal it does not have", () => {
    expect(formatBytes(450_000_000, "en")).toBe("450 MB");
  });

  it("is not an error for nonsense", () => {
    expect(formatBytes(undefined, "en")).toBe("0 MB");
    expect(formatBytes(-5, "en")).toBe("0 MB");
  });
});

const TRACK = (extra) => ({
  id: "t",
  title: "Track",
  artist: "Angerfist",
  album: "Close Combat",
  duration: 210,
  size: 1_000_000,
  state: "done",
  ...extra,
});

describe("groupDownloads", () => {
  it("puts an album's tracks in one group and adds their sizes up", () => {
    const groups = groupDownloads([TRACK({ id: "1" }), TRACK({ id: "2", size: 2_000_000 })]);

    expect(groups).toHaveLength(1);
    expect(groups[0].title).toBe("Close Combat");
    expect(groups[0].subtitle).toBe("Angerfist");
    expect(groups[0].items).toHaveLength(2);
    expect(groups[0].bytes).toBe(3_000_000);
    expect(groups[0].estimated).toBe(false);
  });

  // Grouping a two-hour recording under the album it nominally belongs to
  // buries the one row anybody came to this screen for.
  it("gives a set a group of its own, under its own title", () => {
    const groups = groupDownloads([
      TRACK({ id: "1" }),
      TRACK({ id: "2", title: "Defqon.1 2024", duration: 5400, size: 200_000_000 }),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups[1].isSet).toBe(true);
    expect(groups[1].title).toBe("Defqon.1 2024");
    expect(groups[1].items).toHaveLength(1);
  });

  it("keeps two sets from one album apart", () => {
    const groups = groupDownloads([
      TRACK({ id: "1", title: "Set A", duration: 3600 }),
      TRACK({ id: "2", title: "Set B", duration: 3600 }),
    ]);

    expect(groups.map((group) => group.title)).toEqual(["Set A", "Set B"]);
  });

  it("keeps two artists' loose tracks apart when neither names an album", () => {
    const groups = groupDownloads([
      TRACK({ id: "1", album: "", artist: "Angerfist", title: "One" }),
      TRACK({ id: "2", album: "", artist: "Radical Redemption", title: "Two" }),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("marks a group estimated as soon as one of its items is", () => {
    const groups = groupDownloads([
      TRACK({ id: "1" }),
      TRACK({ id: "2", size: undefined, bitRate: 320 }),
    ]);

    expect(groups[0].estimated).toBe(true);
  });

  it("is an empty list for nothing at all", () => {
    expect(groupDownloads(undefined)).toEqual([]);
  });
});

describe("groupState", () => {
  // The row somebody has to act on is the one that is worth showing. Rolling a
  // single failure up to "done" is how a missing track is discovered in a
  // tunnel instead of at home.
  it("shows the worst state in the group", () => {
    expect(groupState({ items: [{ state: "done" }, { state: "failed" }] })).toBe("failed");
    expect(groupState({ items: [{ state: "done" }, { state: "running" }] })).toBe("running");
    expect(groupState({ items: [{ state: "done" }, { state: "queued" }] })).toBe("queued");
    expect(groupState({ items: [{ state: "done" }, { state: "done" }] })).toBe("done");
  });

  it("reads a missing state as not downloaded", () => {
    expect(groupState({ items: [{ state: "done" }, {}] })).toBe("none");
    expect(groupState(undefined)).toBe("none");
  });
});

describe("groupProgress", () => {
  it("averages the per-item percentages, counting a finished item as whole", () => {
    expect(groupProgress({ items: [{ state: "done" }, { state: "running", progress: 50 }] })).toBe(
      75,
    );
  });

  it("reads a download with no content length as no progress yet", () => {
    expect(groupProgress({ items: [{ state: "running" }] })).toBe(0);
  });

  it("is zero for an empty group", () => {
    expect(groupProgress({ items: [] })).toBe(0);
  });
});
