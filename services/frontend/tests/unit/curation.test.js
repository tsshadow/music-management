import { describe, it, expect } from "vitest";
import {
  isMbid,
  mbidUrl,
  EXTERNAL_SOURCES,
  parentIsAllowed,
  addParent,
  removeParent,
  affectedLabel,
  canEditGenre,
} from "../../src/lib/curation/curation";

describe("isMbid", () => {
  it("accepts a MusicBrainz id", () => {
    expect(isMbid("5b11f4ce-a62d-471e-81fc-a69a8278c7da")).toBe(true);
  });

  it("accepts one in upper case, since MusicBrainz prints both", () => {
    expect(isMbid("5B11F4CE-A62D-471E-81FC-A69A8278C7DA")).toBe(true);
  });

  it("rejects a pasted MusicBrainz URL rather than silently storing it", () => {
    expect(isMbid("https://musicbrainz.org/artist/5b11f4ce-a62d-471e-81fc-a69a8278c7da")).toBe(
      false,
    );
  });

  it("rejects a truncated id", () => {
    expect(isMbid("5b11f4ce-a62d-471e-81fc")).toBe(false);
  });

  it('treats an empty field as "no id", not as an invalid one', () => {
    expect(isMbid("")).toBe(true);
    expect(isMbid(null)).toBe(true);
  });
});

describe("mbidUrl", () => {
  it("links an artist id to the artist page", () => {
    expect(mbidUrl("artist", "5b11f4ce-a62d-471e-81fc-a69a8278c7da")).toBe(
      "https://musicbrainz.org/artist/5b11f4ce-a62d-471e-81fc-a69a8278c7da",
    );
  });

  it("has no link to offer without an id", () => {
    expect(mbidUrl("artist", "")).toBe(null);
  });
});

describe("EXTERNAL_SOURCES", () => {
  it("offers the platforms MuMa already stores ids for", () => {
    expect(EXTERNAL_SOURCES).toContain("spotify");
    expect(EXTERNAL_SOURCES).toContain("soundcloud");
  });

  it("leaves musicbrainz out, because the MBID field owns it", () => {
    // Two inputs writing the same row would let the page disagree with itself.
    expect(EXTERNAL_SOURCES).not.toContain("musicbrainz");
  });
});

describe("parentIsAllowed", () => {
  it("refuses a genre as its own parent", () => {
    expect(parentIsAllowed("Hardcore", "Hardcore", [])).toBe(false);
  });

  it("refuses it regardless of casing and punctuation", () => {
    expect(parentIsAllowed("Uptempo Hardcore", "UPTEMPO-HARDCORE", [])).toBe(false);
  });

  it("still treats a genre spelled without the separator as a different one", () => {
    // The tagger does too: 'hard style' and 'hardstyle' are two genres, and the page
    // must not quietly merge them by being cleverer than the rule it feeds.
    expect(parentIsAllowed("Hardstyle", "hard style", [])).toBe(true);
  });

  it("refuses a parent that is already in the list", () => {
    expect(parentIsAllowed("Industrial Hardcore", "Hardcore", ["Hardcore"])).toBe(false);
  });

  it("allows a genuinely new parent", () => {
    expect(parentIsAllowed("Industrial Hardcore", "Hardcore", ["Terror"])).toBe(true);
  });

  it("refuses an empty parent", () => {
    expect(parentIsAllowed("Industrial Hardcore", "   ", [])).toBe(false);
  });
});

describe("addParent and removeParent", () => {
  it("adds a parent without mutating the list it was given", () => {
    const before = ["Terror"];
    const after = addParent(before, "Hardcore");
    expect(after).toEqual(["Terror", "Hardcore"]);
    expect(before).toEqual(["Terror"]);
  });

  it("trims what it stores", () => {
    expect(addParent([], "  Hardcore  ")).toEqual(["Hardcore"]);
  });

  it("removes by normalized name, so casing does not strand a row", () => {
    expect(removeParent(["Hardcore", "Terror"], "hardcore")).toEqual(["Terror"]);
  });
});

describe("affectedLabel", () => {
  it("says nothing is affected when nothing is", () => {
    expect(affectedLabel(0)).toBe("no tracks");
  });

  it("keeps the singular readable", () => {
    expect(affectedLabel(1)).toBe("1 track");
  });

  it("counts the rest", () => {
    expect(affectedLabel(143)).toBe("143 tracks");
  });
});

describe("canEditGenre", () => {
  it("an accepted genre can be edited", () => {
    expect(canEditGenre({ state: "white" })).toBe(true);
  });

  it("a rejected genre cannot: curation decides it is not in the library", () => {
    expect(canEditGenre({ state: "black" })).toBe(false);
  });

  it("an undecided genre cannot either, because curation comes first", () => {
    expect(canEditGenre({ state: "unknown" })).toBe(false);
  });

  it("nothing at all cannot be edited", () => {
    expect(canEditGenre(null)).toBe(false);
  });
});
