import { describe, it, expect } from "vitest";
import {
  fileName,
  folderOf,
  formatSummary,
  hasFileDetails,
  tagRows,
} from "../../src/lib/trackFile.js";

const WORDS = { mono: "mono", stereo: "stereo", channels: (count) => `${count} kanalen` };

describe("fileName / folderOf", () => {
  it("splits a library-relative path into folder and file", () => {
    expect(fileName("Soundcloud/Complex/Complex - Rammeroni.mp3")).toBe("Complex - Rammeroni.mp3");
    expect(folderOf("Soundcloud/Complex/Complex - Rammeroni.mp3")).toBe("Soundcloud/Complex");
  });

  it("copes with a file at the root and with no path at all", () => {
    expect(fileName("track.flac")).toBe("track.flac");
    expect(folderOf("track.flac")).toBe("");
    expect(fileName(null)).toBe("");
    expect(folderOf(undefined)).toBe("");
  });
});

describe("formatSummary", () => {
  it("prints format, bitrate, sample rate, bit depth, channels and size in that order", () => {
    const text = formatSummary(
      {
        suffix: "flac",
        bitRate: 1011,
        samplingRate: 44100,
        bitDepth: 16,
        channelCount: 2,
        size: 39707434,
      },
      WORDS,
    );
    expect(text).toBe("FLAC · 1011 kbps · 44.1 kHz · 16 bit · stereo · 39.7 MB");
  });

  it("drops a zero bit depth: LMS sends 0 for lossy formats, which is not a depth", () => {
    const text = formatSummary(
      { suffix: "mp3", bitRate: 320, samplingRate: 48000, bitDepth: 0, channelCount: 1 },
      WORDS,
    );
    expect(text).toBe("MP3 · 320 kbps · 48 kHz · mono");
  });

  it("names more than two channels by count", () => {
    expect(formatSummary({ channelCount: 6 }, WORDS)).toBe("6 kanalen");
  });

  it("is empty for a track with nothing known", () => {
    expect(formatSummary({}, WORDS)).toBe("");
    expect(formatSummary(null, WORDS)).toBe("");
    expect(hasFileDetails({})).toBe(false);
    expect(hasFileDetails({ created: "2026-09-02T10:00:00Z" })).toBe(true);
  });
});

describe("tagRows", () => {
  const details = {
    channels: [{ platform: "soundcloud", name: "Complex", label: null, artist: "Complex" }],
    source_url: "https://soundcloud.com/complex/x",
    source: "LABEL",
    bpm: 103.4,
    ml_genre: "hardstyle",
    tags: {
      title: ["Rammeroni Style (Extended Mix)"],
      artist: ["Complex", "EZG"],
      publisher: ["QDance"],
      catalognumber: ["Q404PRO"],
      copyright: ["QDance (2026)"],
      original_artist: ["Complex & EZG"],
      podcast_episode: ["12"],
      isrc: ["NLF712600001"],
    },
  };

  it("puts the provenance first, then the named tags, then whatever is left as raw lines", () => {
    const rows = tagRows(details, {});
    expect(rows.map((r) => r.key)).toEqual([
      "channel",
      "sourceUrl",
      "origin",
      "bpm",
      "catalogNumber",
      "copyright",
      "originalArtist",
      "mlGenre",
      "isrc",
      "podcast_episode",
    ]);
    expect(rows[0].value).toBe("Complex (Soundcloud)");
    expect(rows[0].view).toBe("search:Complex");
    expect(rows[1].href).toBe("https://soundcloud.com/complex/x");
    expect(rows[2].value).toBe("Label");
    expect(rows[3].value).toBe("103");
    expect(rows.find((r) => r.key === "isrc")).toEqual({
      key: "isrc",
      value: "NLF712600001",
      raw: true,
    });
  });

  it("sends a channel curated as a label to that label, and an uncurated one nowhere", () => {
    const rows = tagRows(
      {
        channels: [
          { platform: "youtube", name: "Q-dance", label: "Q-dance Records", artist: null },
          { platform: "youtube", name: "Random Uploads", label: null, artist: null },
        ],
      },
      {},
    );
    expect(rows[0].view).toBe("label:Q-dance Records");
    expect(rows[1].view).toBeUndefined();
  });

  it("does not repeat tags the sheet already renders as chips or rows", () => {
    const keys = tagRows(details, {}).map((r) => r.key);
    for (const shown of ["title", "artist", "publisher"]) expect(keys).not.toContain(shown);
  });

  it("shows MuMa's effective BPM with ≈ when it is not measured (issue #141)", () => {
    const coarse = tagRows({ bpm: 152, bpm_approximate: true, tags: { bpm: ["76"] } }, {});
    expect(coarse).toEqual([{ key: "bpm", value: "≈152" }]);
    const measured = tagRows({ bpm: 150.02, bpm_approximate: false }, {});
    expect(measured).toEqual([{ key: "bpm", value: "150" }]);
  });

  it("falls back to the tagged bpm and the LMS comment when MuMa has neither", () => {
    const rows = tagRows({ tags: { bpm: ["150"] } }, { comment: " hello " });
    expect(rows).toEqual([
      { key: "bpm", value: "150" },
      { key: "comment", value: "hello" },
    ]);
  });

  it("is empty without an answer from MuMa and nothing on the song", () => {
    expect(tagRows(null, {})).toEqual([]);
    expect(tagRows(undefined, null)).toEqual([]);
  });

  it("skips tags whose every value is blank", () => {
    expect(tagRows({ tags: { isrc: ["", "  "] } }, {})).toEqual([]);
  });
});
