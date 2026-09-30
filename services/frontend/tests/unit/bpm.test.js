import { describe, it, expect, vi } from "vitest";
import {
  bpmContinuation,
  bpmQuery,
  countNear,
  fillBins,
  formatBpm,
  loadBpmPage,
  parseBpm,
  peakCount,
  selectionParams,
  withBpm,
} from "../../src/lib/bpm.js";

const TRACKS = [
  {
    id: 1,
    library_path: "EPs/A/1.mp3",
    bpm: 152,
    bpm_source: "tag",
    bpm_confidence: "medium",
    bpm_folded: false,
    bpm_approximate: true,
  },
  {
    id: 2,
    library_path: "EPs/A/2.mp3",
    bpm: 150.02,
    bpm_source: "measured",
    bpm_confidence: "high",
    bpm_folded: false,
    bpm_approximate: false,
  },
];

describe("bpm.js", () => {
  it("asks for a tempo with its tolerance, or a range, with the filters", () => {
    expect(selectionParams({ bpm: 150, tol: null, reliable: false, genre: "" })).toEqual({
      bpm: 150,
      tol: null,
      min_confidence: null,
      genre: null,
    });
    expect(
      selectionParams({ bpm: null, from: 140, to: null, reliable: true, genre: "Hardstyle" }),
    ).toEqual({
      bpm_from: 140,
      bpm_to: null,
      min_confidence: "medium",
      genre: "Hardstyle",
    });
    expect(selectionParams({ bpm: null, from: null, to: null })).toBeNull();
  });

  it("leaves empty values out of the query string", () => {
    expect(bpmQuery({ bpm: 150, tol: null, genre: "", min_confidence: undefined })).toBe("bpm=150");
  });

  it("reads a typed tempo, commas included, and refuses nonsense", () => {
    expect(parseBpm("150,5")).toBe(150.5);
    expect(parseBpm(" 175 ")).toBe(175);
    expect(parseBpm("")).toBeNull();
    expect(parseBpm("abc")).toBeNull();
    expect(parseBpm("12")).toBeNull();
  });

  it("writes a coarse value with ≈ and a measurement plain", () => {
    expect(formatBpm({ bpm: 151.999, approximate: true })).toBe("≈152");
    expect(formatBpm({ bpm: 150.02, approximate: false })).toBe("150");
    expect(formatBpm(null)).toBe("");
  });

  it("reads the API's numeric strings and 0/1 flags, and prints nothing for no BPM", () => {
    // /api/library/advanced sends `bpm_approximate` as the database's 0/1 (issue #141).
    expect(formatBpm({ bpm: "152.00", approximate: 1 })).toBe("≈152");
    expect(formatBpm({ bpm: 150, approximate: 0 })).toBe("150");
    expect(formatBpm({ bpm: null, approximate: null })).toBe("");
    expect(formatBpm({ bpm: "", approximate: 1 })).toBe("");
    expect(formatBpm({ bpm: 0 })).toBe("");
  });

  it("attaches the BPM to the songs by path and leaves strangers alone", () => {
    const songs = withBpm(
      [
        { id: "a", path: "EPs/A/2.mp3" },
        { id: "b", path: "Other/root.mp3" },
      ],
      TRACKS,
    );
    expect(songs[0].mumaBpm).toEqual({
      bpm: 150.02,
      source: "measured",
      confidence: "high",
      folded: false,
      approximate: false,
    });
    expect(songs[1].mumaBpm).toBeUndefined();
  });

  it("loads a page: MuMa's tracks resolved to songs through LMS", async () => {
    const fetchPage = vi.fn(async () => ({ tracks: TRACKS, total: 7, next_offset: 2 }));
    const resolve = vi.fn(async (paths) => ({
      songs: paths.slice(0, 1).map((path) => ({ id: path, path })),
      failed: false,
    }));
    const page = await loadBpmPage({ bpm: 150 }, "u=x", 0, { fetchPage, resolve });
    expect(resolve).toHaveBeenCalledWith(["EPs/A/1.mp3", "EPs/A/2.mp3"], "u=x");
    expect(page).toMatchObject({
      total: 7,
      nextOffset: 2,
      unresolved: 1,
      approximate: true,
      failed: false,
    });
    expect(page.songs[0].mumaBpm.bpm).toBe(152);
  });

  it("reports a failure instead of an empty list when MuMa or LMS cannot be asked", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const down = await loadBpmPage({ bpm: 150 }, "u=x", 100, {
      fetchPage: vi.fn(async () => {
        throw new Error("offline");
      }),
    });
    expect(down).toMatchObject({ failed: true, nextOffset: 100 });
    const lmsDown = await loadBpmPage({ bpm: 150 }, "u=x", 0, {
      fetchPage: vi.fn(async () => ({ tracks: TRACKS, total: 2, next_offset: null })),
      resolve: vi.fn(async () => ({ songs: [], failed: true })),
    });
    expect(lmsDown.failed).toBe(true);
    expect(lmsDown.unresolved).toBe(0);
  });

  it("continues a queue with the next page and keeps its place after a failure", async () => {
    expect(bpmContinuation({ bpm: 150 }, null, () => "u=x")).toBeNull();
    const loadPage = vi
      .fn()
      .mockResolvedValueOnce({ failed: true })
      .mockResolvedValueOnce({ failed: false, songs: [{ id: 9 }], nextOffset: null });
    const continuation = bpmContinuation({ bpm: 150 }, 100, () => "u=x", { loadPage });
    expect(continuation.kind).toBe("bpm");
    expect(await continuation.fetchNext(100)).toEqual({ tracks: [], cursor: 100, failed: true });
    expect(await continuation.fetchNext(100)).toEqual({ tracks: [{ id: 9 }], cursor: null });
    expect(loadPage).toHaveBeenCalledWith({ bpm: 150 }, "u=x", 100);
  });

  it("fills the histogram with zeroes so every bar stands at its tempo", () => {
    const bars = fillBins([{ bpm: 152, count: 5, high: 0, medium: 1, low: 4 }], 150, 153);
    expect(bars.map((bar) => [bar.bpm, bar.count])).toEqual([
      [150, 0],
      [151, 0],
      [152, 5],
      [153, 0],
    ]);
    expect(peakCount([])).toBe(1);
    expect(peakCount(bars)).toBe(5);
  });

  it("counts what a chip would find within its tolerance", () => {
    const bins = [
      { bpm: 148, count: 1 },
      { bpm: 152, count: 5 },
      { bpm: 156, count: 3 },
    ];
    expect(countNear(bins, 150, 2)).toBe(6);
    expect(countNear(bins, 155, 1)).toBe(3);
  });
});
