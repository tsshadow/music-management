import { describe, it, expect } from "vitest";
import { stationAsTrack, stationFromNativeState } from "../../src/lib/liveStation.js";

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
