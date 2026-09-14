import { describe, it, expect } from "vitest";
import {
  normalizePreset,
  presetQuery,
  presetParamsFromFilters,
  presetSummary,
} from "../../src/lib/presets.js";

/**
 * A preset is a saved query, and MuMa stores two spellings of one: the tile the
 * Kotlin app writes (`genre`, `sortMethod`, `ratingMin`, `length`) and the
 * shape the management tab writes (`genres`, `sort_method`, `rating_range`,
 * `song_type`). Both have to come out of `normalizePreset` as the same thing,
 * and what the web writes has to be a tile the Kotlin app still understands.
 */
describe("normalizePreset", () => {
  it("reads a Kotlin tile", () => {
    const preset = normalizePreset({
      id: 7,
      name: "Random Uptempo",
      params: JSON.stringify({
        pageKey: "songs",
        genre: ["Uptempo Hardcore", "Bouncy Uptempo"],
        year: ["2024"],
        size: 200,
        sortMethod: "Random",
        ratingMin: 3,
        ratingMax: 5,
        length: "short",
      }),
    });

    expect(preset).toEqual({
      id: "7",
      name: "Random Uptempo",
      genres: ["Uptempo Hardcore", "Bouncy Uptempo"],
      years: ["2024"],
      artists: [],
      labels: [],
      festivals: [],
      sort: "random",
      minRating: 3,
      maxRating: 5,
      length: "short",
      size: 200,
    });
  });

  it("reads what the management tab wrote", () => {
    const preset = normalizePreset({
      id: 3,
      name: "Hardstyle",
      params: JSON.stringify({
        genres: ["Hardstyle"],
        rating_range: [0, 100],
        size: 500,
        sort_method: "newest",
        song_type: "set",
      }),
    });

    expect(preset.genres).toEqual(["Hardstyle"]);
    expect(preset.sort).toBe("recent");
    expect(preset.minRating).toBe(0);
    expect(preset.maxRating).toBe(5);
    expect(preset.length).toBe("long");
    expect(preset.size).toBe(500);
  });

  it("drops the 'All' placeholder the Kotlin pickers store", () => {
    const preset = normalizePreset({
      id: 1,
      name: "x",
      params: JSON.stringify({ genre: ["All"], year: ["All", "2023"] }),
    });
    expect(preset.genres).toEqual([]);
    expect(preset.years).toEqual(["2023"]);
  });

  it("survives params that are not JSON", () => {
    const preset = normalizePreset({ id: 9, name: "broken", params: "genre=Hardcore" });
    expect(preset.name).toBe("broken");
    expect(preset.genres).toEqual([]);
    expect(preset.sort).toBe("recent");
  });

  it("leaves the mode open when the tile has no length", () => {
    const preset = normalizePreset({ id: 2, name: "y", params: "{}" });
    expect(preset.length).toBeNull();
  });
});

describe("presetQuery", () => {
  const base = normalizePreset({
    id: 1,
    name: "Recent Raw",
    params: JSON.stringify({
      genre: ["Raw Hardstyle"],
      year: ["2023", "2024"],
      artists: ["Warface"],
      label: ["End of Line"],
      sortMethod: "DateDescAndRelease",
      ratingMin: 2,
      length: "short",
      size: 100,
    }),
  });

  it("builds the getSongs call the Kotlin app makes", () => {
    const { method, params } = presetQuery(base, { viewMode: "songs" });

    expect(method).toBe("getSongs");
    expect(JSON.parse(params.clusters)).toEqual([
      { name: "GENRE", value: ["Raw Hardstyle"] },
      { name: "YEAR", value: ["2023", "2024"] },
      { name: "ARTIST", value: ["Warface"] },
      { name: "PUBLISHER", value: ["End of Line"] },
      { name: "LENGTH", value: "short" },
    ]);
    expect(params.sortMethod).toBe("DateDescAndRelease");
    expect(params.ratingMin).toBe(2);
    expect(params.ratingMax).toBeUndefined();
    expect(params.count).toBe(100);
    expect(params.offset).toBe(0);
  });

  it("takes the length from the listener's mode when the tile has none", () => {
    const open = { ...base, length: null };
    const songs = JSON.parse(presetQuery(open, { viewMode: "songs" }).params.clusters);
    const sets = JSON.parse(presetQuery(open, { viewMode: "sets" }).params.clusters);
    expect(songs.at(-1)).toEqual({ name: "LENGTH", value: "short" });
    expect(sets.at(-1)).toEqual({ name: "LENGTH", value: "long" });
  });

  it("seeds a random sort so paging stays on one shuffle", () => {
    const { params } = presetQuery(
      { ...base, sort: "random" },
      { viewMode: "songs", seed: 42, offset: 50 },
    );
    expect(params.sortMethod).toBe("Random");
    expect(params.seed).toBe(42);
    expect(params.offset).toBe(50);
  });

  it("omits a rating floor of zero", () => {
    const { params } = presetQuery({ ...base, minRating: 0 }, { viewMode: "songs" });
    expect(params.ratingMin).toBeUndefined();
  });
});

describe("presetParamsFromFilters", () => {
  it("writes a tile the Kotlin app can open", () => {
    const params = JSON.parse(
      presetParamsFromFilters({
        genre: "Uptempo Hardcore",
        year: "2024",
        sort: "random",
        minRating: "3",
        viewMode: "songs",
      }),
    );

    expect(params).toEqual({
      pageKey: "songs",
      genre: ["Uptempo Hardcore"],
      year: ["2024"],
      sortMethod: "Random",
      ratingMin: 3,
      ratingMax: 5,
      length: "short",
      size: 500,
    });
  });

  it("leaves out what was not filtered on", () => {
    const params = JSON.parse(
      presetParamsFromFilters({
        genre: "",
        year: "",
        sort: "recent",
        minRating: "0",
        viewMode: "sets",
      }),
    );
    expect(params.genre).toBeUndefined();
    expect(params.year).toBeUndefined();
    expect(params.ratingMin).toBeUndefined();
    expect(params.length).toBe("long");
    expect(params.sortMethod).toBe("DateDescAndRelease");
  });

  it("round-trips through normalizePreset", () => {
    const params = presetParamsFromFilters({
      genre: "Hardstyle",
      label: "Scantraxx",
      year: "",
      sort: "added",
      minRating: "4",
      viewMode: "songs",
    });
    const preset = normalizePreset({ id: 5, name: "n", params });
    expect(preset.genres).toEqual(["Hardstyle"]);
    expect(preset.labels).toEqual(["Scantraxx"]);
    expect(preset.sort).toBe("added");
    expect(preset.minRating).toBe(4);
  });
});

describe("presetSummary", () => {
  const t = (key, vars) => (vars ? `${key}:${JSON.stringify(vars)}` : key);

  it("names the filters in one line", () => {
    const preset = normalizePreset({
      id: 1,
      name: "x",
      params: JSON.stringify({
        genre: ["Hardcore", "Frenchcore"],
        year: ["2024"],
        sortMethod: "Random",
        ratingMin: 3,
      }),
    });
    expect(presetSummary(preset, t)).toBe(
      'sort.random · Hardcore, Frenchcore · 2024 · filter.starsMin:{"count":3}',
    );
  });

  it("says so when there is no filter at all", () => {
    const preset = normalizePreset({ id: 1, name: "x", params: "{}" });
    expect(presetSummary(preset, t)).toBe("sort.recentlyReleased · presets.everything");
  });
});
