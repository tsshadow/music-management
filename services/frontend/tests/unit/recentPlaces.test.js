import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { get } from "svelte/store";
import { credentials } from "../../src/lib/store.js";
import {
  recentPlaces,
  recordPlace,
  placeTitle,
  clearRecentPlaces,
  PLACE_PREFIXES,
} from "../../src/lib/recentPlaces.js";

describe("recentPlaces", () => {
  beforeEach(() => {
    localStorage.clear();
    credentials.set({ url: "https://muma.test", username: "user", password: "pw" });
  });

  afterEach(() => {
    clearRecentPlaces();
  });

  it("keeps recorded places newest first", () => {
    recordPlace("genre:Hardcore", "Hardcore");
    recordPlace("label:Art of Creation", "Art of Creation");

    expect(get(recentPlaces).map((p) => p.view)).toEqual([
      "label:Art of Creation",
      "genre:Hardcore",
    ]);
  });

  it("dedupes a repeat, moving it to the front and updating a given title", () => {
    recordPlace("genre:Hardcore", "Hardcore");
    recordPlace("label:Art of Creation", "Art of Creation");
    recordPlace("genre:Hardcore", "Hardcore (edited)");

    const places = get(recentPlaces);
    expect(places).toHaveLength(2);
    expect(places[0]).toMatchObject({ view: "genre:Hardcore", title: "Hardcore (edited)" });
  });

  it("keeps the existing title when a repeat carries none", () => {
    recordPlace("artist:1", "Angerfist");
    recordPlace("artist:1");

    expect(get(recentPlaces)[0]).toMatchObject({ view: "artist:1", title: "Angerfist" });
  });

  it("caps the list at 12, dropping the oldest", () => {
    for (let i = 0; i < 13; i++) {
      recordPlace(`artist:${i}`, `Artist ${i}`);
    }

    const places = get(recentPlaces);
    expect(places).toHaveLength(12);
    expect(places.map((p) => p.view)).not.toContain("artist:0");
    expect(places[0].view).toBe("artist:12");
  });

  it("ignores a view outside PLACE_PREFIXES", () => {
    recordPlace("settings");
    recordPlace("songs");

    expect(get(recentPlaces)).toEqual([]);
    // Sanity check the fixture list itself names what the feature covers.
    expect(PLACE_PREFIXES).toContain("genre:");
  });

  it("isolates the list per server and account", () => {
    recordPlace("genre:Hardcore", "Hardcore");
    expect(get(recentPlaces)).toHaveLength(1);

    credentials.set({ url: "https://muma.test", username: "sanne", password: "pw" });
    expect(get(recentPlaces)).toEqual([]);

    recordPlace("genre:Trance", "Trance");
    expect(get(recentPlaces).map((p) => p.view)).toEqual(["genre:Trance"]);

    // Switching back to the first account restores that account's own list, not sanne's.
    credentials.set({ url: "https://muma.test", username: "user", password: "pw" });
    expect(get(recentPlaces).map((p) => p.view)).toEqual(["genre:Hardcore"]);
  });

  it("is empty and writes nothing while signed out", () => {
    credentials.set({ url: "https://muma.test", username: "", password: "" });
    recordPlace("genre:Hardcore", "Hardcore");

    expect(get(recentPlaces)).toEqual([]);
  });

  it("keeps working in memory when localStorage throws", () => {
    const spy = vi.spyOn(localStorage, "setItem").mockImplementation(() => {
      throw new Error("private mode");
    });

    expect(() => recordPlace("genre:Hardcore", "Hardcore")).not.toThrow();
    expect(get(recentPlaces).map((p) => p.view)).toEqual(["genre:Hardcore"]);

    spy.mockRestore();
  });

  it("survives a throwing localStorage read on a credentials switch", () => {
    recordPlace("genre:Hardcore", "Hardcore");
    const spy = vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new Error("private mode");
    });

    expect(() =>
      credentials.set({ url: "https://muma.test", username: "other", password: "pw" }),
    ).not.toThrow();
    expect(get(recentPlaces)).toEqual([]);

    spy.mockRestore();
  });

  describe("placeTitle", () => {
    it("prefers a stored title", () => {
      expect(placeTitle({ view: "genre:Hardcore", title: "Hard Techno" })).toBe("Hard Techno");
    });

    it("reads the argument for genre, label, festival, year and memories", () => {
      expect(placeTitle({ view: "genre:Hardcore" })).toBe("Hardcore");
      expect(placeTitle({ view: "label:Art of Creation" })).toBe("Art of Creation");
      expect(placeTitle({ view: "festival:Defqon.1" })).toBe("Defqon.1");
      expect(placeTitle({ view: "year:2019" })).toBe("2019");
      expect(placeTitle({ view: "memories:2024" })).toBe("2024");
    });

    it("is null for an id-based place with no title yet", () => {
      expect(placeTitle({ view: "artist:123" })).toBeNull();
      expect(placeTitle({ view: "playlist:9" })).toBeNull();
    });

    it("is null for nothing at all", () => {
      expect(placeTitle(null)).toBeNull();
    });
  });
});
