import { describe, it, expect } from "vitest";
import { describeImportConflict, groupByLabel } from "../../src/lib/management/labelProposals";

describe("groupByLabel", () => {
  it("puts every release of one proposed label in a single group", () => {
    const groups = groupByLabel([
      { id: 1, folder: "a", proposed_label: "Brutal Kuts" },
      { id: 2, folder: "b", proposed_label: "Brutal Kuts" },
      { id: 3, folder: "c", proposed_label: "Traxtorm Records" },
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Brutal Kuts", "Traxtorm Records"]);
    expect(groups[0].proposals).toHaveLength(2);
  });

  it("collects the proposals without a label into their own group, last", () => {
    const groups = groupByLabel([
      { id: 1, folder: "a", proposed_label: null },
      { id: 2, folder: "b", proposed_label: "Brutal Kuts" },
    ]);

    expect(groups[1].label).toBe(null);
  });

  it("sorts the labelled groups by name so the list does not reshuffle between loads", () => {
    const groups = groupByLabel([
      { id: 1, folder: "a", proposed_label: "Traxtorm Records" },
      { id: 2, folder: "b", proposed_label: "Brutal Kuts" },
    ]);

    expect(groups.map((g) => g.label)).toEqual(["Brutal Kuts", "Traxtorm Records"]);
  });

  it("returns nothing for an empty list", () => {
    expect(groupByLabel([])).toEqual([]);
  });
});

describe("describeImportConflict", () => {
  it("names a folder pair by the target that is taken", () => {
    expect(
      describeImportConflict({ step: "renamer", source: "/i/a", target: "/i/b", reason: null }),
    ).toEqual({
      key: "conflictTaken",
      detail: "/i/b",
    });
  });

  it("names a file the extractor left by its reason", () => {
    expect(
      describeImportConflict({
        step: "extractor",
        source: "/i/clip.mp4",
        target: "",
        reason: "not-music-video",
      }),
    ).toEqual({ key: "conflictReasons.not-music-video", detail: "" });
  });

  it("keeps the detail of a failed extraction", () => {
    const row = {
      step: "extractor",
      source: "/i/a.zip",
      target: "every backend failed",
      reason: "extraction-failed",
    };
    expect(describeImportConflict(row).detail).toBe("every backend failed");
  });

  it("falls back to a generic line for a reason it does not know", () => {
    expect(
      describeImportConflict({ step: "extractor", source: "/i/x", target: "", reason: "new-code" })
        .key,
    ).toBe("conflictReasons.unknown");
  });
});
