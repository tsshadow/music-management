import { describe, it, expect } from "vitest";
import { COLLECTION_MODES, itemsForMode } from "../../src/lib/collections.js";

const LIBRARY = [
  { id: "artists" },
  { id: "albums" },
  { id: "genres" },
  { id: "labels" },
  { id: "podcasts" },
  { id: "festivals" },
  { id: "years" },
  { id: "lineups" },
];

const idsIn = (mode) => itemsForMode(LIBRARY, mode).map((item) => item.id);

describe("browse views per mode", () => {
  it("offers the release-shaped views in song mode", () => {
    expect(idsIn("songs")).toEqual(["artists", "albums", "genres", "labels", "years", "lineups"]);
  });

  it("offers the recording-shaped views in set mode", () => {
    expect(idsIn("sets")).toEqual([
      "artists",
      "albums",
      "genres",
      "podcasts",
      "festivals",
      "years",
    ]);
  });

  // The tagger writes neither tag below ten minutes, so these two lists cannot hold
  // a single track that song mode would query for.
  it.each(["podcasts", "festivals"])("keeps %s out of song mode", (id) => {
    expect(idsIn("songs")).not.toContain(id);
  });

  it.each(["labels", "lineups"])("keeps %s out of set mode", (id) => {
    expect(idsIn("sets")).not.toContain(id);
  });

  it.each(["artists", "albums", "genres", "years"])("shows %s in both modes", (id) => {
    expect(idsIn("songs")).toContain(id);
    expect(idsIn("sets")).toContain(id);
    expect(COLLECTION_MODES[id]).toBeUndefined();
  });

  it("leaves a list it knows nothing about alone", () => {
    expect(itemsForMode([{ id: "starred" }], "songs")).toEqual([{ id: "starred" }]);
  });
});
