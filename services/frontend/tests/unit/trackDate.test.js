import { describe, expect, it } from "vitest";

import { formatShortDate, preferredReleaseDate, releaseDateLabel } from "../../src/lib/trackDate.js";

/**
 * The case that prompted this: a scene tag of `2026-00-00` reaches LMS as `date = "2026"`,
 * while the release date MuMa resolved from the NFO travels as `originalDate = "2026-09-03"`.
 * The list sorted on the original date and the row printed the edition date, so the same
 * track claimed two different things on one screen.
 */
describe("preferredReleaseDate", () => {
  it("prefers the original date when it is more precise", () => {
    expect(preferredReleaseDate("2026", "2026-09-03")).toBe("2026-09-03");
  });

  it("keeps the edition date when the original is less precise", () => {
    expect(preferredReleaseDate("2024-07-28", "2024")).toBe("2024-07-28");
  });

  it("prefers the original when both are equally precise", () => {
    expect(preferredReleaseDate("2024-01-02", "2023-05-06")).toBe("2023-05-06");
  });

  it("falls back to the edition date when there is no original", () => {
    expect(preferredReleaseDate("2026-09-03", "")).toBe("2026-09-03");
    expect(preferredReleaseDate("2026-09-03", undefined)).toBe("2026-09-03");
  });
});

describe("formatShortDate", () => {
  it("turns a full date around", () => {
    expect(formatShortDate("2026-09-03")).toBe("03-09-2026");
  });

  it("drops the time part of a timestamp", () => {
    expect(formatShortDate("2026-09-03T18:46:35")).toBe("03-09-2026");
  });

  it("returns null for a year, so the caller can show its own", () => {
    expect(formatShortDate("2026")).toBeNull();
    expect(formatShortDate("")).toBeNull();
  });
});

describe("releaseDateLabel", () => {
  it("shows the original date of a track whose edition date is only a year", () => {
    expect(releaseDateLabel({ date: "2026", originalDate: "2026-09-03", year: 2026 })).toBe("03-09-2026");
  });

  it("falls back to the year when neither date is precise", () => {
    expect(releaseDateLabel({ date: "2026", originalDate: "", year: 2026 })).toBe(2026);
  });

  it("shows nothing rather than undefined when the track has no date at all", () => {
    expect(releaseDateLabel({})).toBe("");
    expect(releaseDateLabel(null)).toBe("");
  });
});
