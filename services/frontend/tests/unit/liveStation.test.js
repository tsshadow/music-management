import { describe, it, expect } from "vitest";
import {
  RECENT_STATIONS_KEPT,
  stationAsTrack,
  stationFromNativeState,
  stationLogoUrl,
  stationSections,
  withFavoriteToggled,
  withRecentStation,
} from "../../src/lib/liveStation.js";

describe("stationAsTrack", () => {
  it("shows the name as the title when the stream sends nothing", () => {
    expect(stationAsTrack({ name: "SLAM", title: null })).toMatchObject({
      id: null,
      title: "SLAM",
      artist: "",
    });
  });

  it("puts the name under the title the stream sends", () => {
    expect(stationAsTrack({ name: "SLAM", title: "Angerfist - Pissed Off" })).toMatchObject({
      title: "Angerfist - Pissed Off",
      artist: "SLAM",
    });
  });

  it("does not show the name twice when the stream repeats it", () => {
    expect(stationAsTrack({ name: "SLAM", title: "SLAM" })).toMatchObject({
      title: "SLAM",
      artist: "",
    });
  });
});

describe("stationFromNativeState", () => {
  const LISTED = [{ slug: "slam", name: "SLAM", stream_url: "https://example.com/slam.mp3" }];

  it("is null when the service plays no station", () => {
    expect(stationFromNativeState({ stationSlug: null }, LISTED, null)).toBeNull();
  });

  it("takes the name and the address from the list", () => {
    expect(
      stationFromNativeState({ stationSlug: "slam", stationTitle: "A - B" }, LISTED, null),
    ).toEqual({
      slug: "slam",
      name: "SLAM",
      stream_url: "https://example.com/slam.mp3",
      title: "A - B",
    });
  });

  it("keeps the name it had when the list is not loaded", () => {
    const current = { slug: "slam", name: "SLAM", stream_url: null };
    expect(
      stationFromNativeState({ stationSlug: "slam", stationTitle: "A - B" }, [], current).name,
    ).toBe("SLAM");
  });

  it("falls back to what the service says for a station started in the car", () => {
    expect(
      stationFromNativeState({ stationSlug: "slam", stationTitle: "SLAM" }, [], null).name,
    ).toBe("SLAM");
  });
});

describe("stationLogoUrl", () => {
  it("names the file by the slug", () => {
    expect(stationLogoUrl("q-dance")).toBe("/images/stations/q-dance.png");
  });
});

describe("withRecentStation", () => {
  it("puts the newest first, once", () => {
    expect(withRecentStation(["a", "b"], "b")).toEqual(["b", "a"]);
  });

  it("keeps a limited number", () => {
    const full = Array.from({ length: RECENT_STATIONS_KEPT }, (_, i) => `s${i}`);
    const next = withRecentStation(full, "new");
    expect(next).toHaveLength(RECENT_STATIONS_KEPT);
    expect(next[0]).toBe("new");
    expect(next).not.toContain(full.at(-1));
  });
});

describe("withFavoriteToggled", () => {
  it("adds a station at the end, and removes it again", () => {
    expect(withFavoriteToggled(["a"], "b")).toEqual(["a", "b"]);
    expect(withFavoriteToggled(["a", "b"], "a")).toEqual(["b"]);
  });
});

describe("stationSections", () => {
  const station = (slug, name = slug) => ({ slug, name });
  const ALL = [station("538"), station("q-dance", "Q-dance"), station("slam", "SLAM")];
  const slugs = (list) => list.map((s) => s.slug);

  it("gives the favorites in the order they were marked", () => {
    expect(slugs(stationSections(ALL, ["slam", "538"], []).favorites)).toEqual(["slam", "538"]);
  });

  it("leaves a favorite out of the recent list", () => {
    expect(slugs(stationSections(ALL, ["slam"], ["slam", "538"]).recent)).toEqual(["538"]);
  });

  it("skips a slug the server no longer lists", () => {
    const sections = stationSections(ALL, ["gone"], ["gone"]);
    expect(sections.favorites).toEqual([]);
    expect(sections.recent).toEqual([]);
  });

  it("keeps every station in the full list", () => {
    expect(slugs(stationSections(ALL, ["slam"], ["538"]).all)).toEqual(slugs(ALL));
  });
});
