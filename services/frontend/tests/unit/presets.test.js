import { describe, it, expect, vi, afterEach } from "vitest";
import {
  DEFAULT_PRESET_SIZE,
  PRESET_SORTS,
  normalizePreset,
  presetParams,
  presetParamsFromFilters,
  presetQuery,
  presetSummary,
  updatePreset,
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
      minQuality: null,
      length: "short",
      form: null,
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

  it("sends a quality floor as every tier down to it", () => {
    const lossless = { ...base, minQuality: "lossless" };
    const kbps320 = { ...base, minQuality: "320" };
    expect(JSON.parse(presetQuery(lossless, { viewMode: "songs" }).params.clusters)).toContainEqual(
      {
        name: "QUALITY",
        value: ["lossless"],
      },
    );
    expect(JSON.parse(presetQuery(kbps320, { viewMode: "songs" }).params.clusters)).toContainEqual({
      name: "QUALITY",
      value: ["lossless", "320"],
    });
  });

  it("sends no quality cluster for a floor it does not know", () => {
    const odd = { ...base, minQuality: "hifi" };
    const clusters = JSON.parse(presetQuery(odd, { viewMode: "songs" }).params.clusters);
    expect(clusters.some((c) => c.name === "QUALITY")).toBe(false);
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
      minQuality: "320",
      viewMode: "songs",
    });
    const preset = normalizePreset({ id: 5, name: "n", params });
    expect(preset.genres).toEqual(["Hardstyle"]);
    expect(preset.labels).toEqual(["Scantraxx"]);
    expect(preset.sort).toBe("added");
    expect(preset.minRating).toBe(4);
    expect(preset.minQuality).toBe("320");
  });

  it("writes no quality key when the filter bar had no floor", () => {
    const params = JSON.parse(
      presetParamsFromFilters({ sort: "recent", minQuality: "", viewMode: "songs" }),
    );
    expect(params.minQuality).toBeUndefined();
    expect(
      normalizePreset({ id: 1, name: "n", params: JSON.stringify(params) }).minQuality,
    ).toBeNull();
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

describe("presetParams", () => {
  it("writes every cluster as a list, in the Kotlin tile spelling", () => {
    const params = JSON.parse(
      presetParams({
        genres: ["Uptempo Hardcore", "Terror"],
        artists: ["Angerfist"],
        labels: ["Masters of Hardcore"],
        festivals: ["Dominator"],
        years: [2024, "2023"],
        sort: "random",
        minRating: 3,
        maxRating: 4,
        viewMode: "sets",
        size: 200,
      }),
    );

    expect(params).toEqual({
      pageKey: "sets",
      genre: ["Uptempo Hardcore", "Terror"],
      artists: ["Angerfist"],
      label: ["Masters of Hardcore"],
      festival: ["Dominator"],
      year: ["2024", "2023"],
      sortMethod: "Random",
      ratingMin: 3,
      ratingMax: 4,
      length: "long",
      size: 200,
    });
  });

  it("leaves out empty lists, blank entries and a 0..5 rating range", () => {
    const params = JSON.parse(presetParams({ genres: [" ", ""], artists: [], viewMode: "songs" }));

    expect(params).toEqual({
      pageKey: "songs",
      sortMethod: "DateDescAndRelease",
      length: "short",
      size: DEFAULT_PRESET_SIZE,
    });
  });

  it("keeps a ceiling below five even without a floor", () => {
    const params = JSON.parse(presetParams({ maxRating: 2, viewMode: "songs" }));
    expect(params.ratingMin).toBe(0);
    expect(params.ratingMax).toBe(2);
  });

  it("round-trips through normalizePreset and into the getSongs clusters", () => {
    const preset = normalizePreset({
      id: 1,
      name: "x",
      params: presetParams({
        genres: ["Hardstyle"],
        artists: ["Sub Zero Project"],
        festivals: ["Defqon.1"],
        years: ["2025"],
        sort: "added",
        viewMode: "songs",
      }),
    });
    const { params } = presetQuery(preset, { viewMode: "songs" });
    const clusters = JSON.parse(params.clusters);

    expect(clusters).toContainEqual({ name: "GENRE", value: ["Hardstyle"] });
    expect(clusters).toContainEqual({ name: "ARTIST", value: ["Sub Zero Project"] });
    expect(clusters).toContainEqual({ name: "FESTIVAL", value: ["Defqon.1"] });
    expect(clusters).toContainEqual({ name: "YEAR", value: ["2025"] });
    expect(params.sortMethod).toBe("AddedDesc");
  });

  it("offers every sort the summary can name", () => {
    expect(PRESET_SORTS.map((s) => s.id)).toEqual([
      "recent",
      "added",
      "random",
      "starred",
      "alpha",
    ]);
  });
});

describe("updatePreset", () => {
  afterEach(() => vi.restoreAllMocks());

  it("PUTs the name and params to the preset's own url", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ status: "ok" }) }));

    await updatePreset(7, "15", { name: "Renamed", params: "{}" });

    const [url, init] = globalThis.fetch.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/users\/7\/dynamic-playlists\/15$/);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ name: "Renamed", params: "{}" });
  });

  it("throws on a refusal", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 403 }));
    await expect(updatePreset(7, "15", { name: "x" })).rejects.toThrow("403");
  });
});

/**
 * The track form a sets preset can carry (issue #47): saved by the builder and the filter bar,
 * read by the web and by Android Auto (`TileInfo.form`), sent to `getSongs` as `form` -- and never
 * a value LMS would refuse the whole request over.
 */
describe("preset track form", () => {
  it("writes the form for a sets preset and round-trips it", () => {
    const params = presetParams({ festivals: ["Defqon.1"], form: "liveset", viewMode: "sets" });
    expect(JSON.parse(params)).toMatchObject({ form: "liveset", length: "long" });

    const preset = normalizePreset({ id: 1, name: "x", params });
    expect(preset.form).toBe("liveset");
  });

  it("never writes a form for a songs preset, or one LMS does not know", () => {
    expect(JSON.parse(presetParams({ form: "liveset", viewMode: "songs" })).form).toBeUndefined();
    expect(JSON.parse(presetParams({ form: "mixtape", viewMode: "sets" })).form).toBeUndefined();
  });

  it("reads an unknown or songs-side form back as none", () => {
    const unknown = normalizePreset({
      id: 1,
      name: "x",
      params: '{"length":"long","form":"mixtape"}',
    });
    const songs = normalizePreset({
      id: 2,
      name: "y",
      params: '{"length":"short","form":"liveset"}',
    });
    expect(unknown.form).toBeNull();
    expect(songs.form).toBeNull();
  });

  it("sends the form to getSongs, with one year as the filing year", () => {
    const preset = normalizePreset({
      id: 1,
      name: "x",
      params: '{"length":"long","festival":["Defqon.1"],"year":["2019"],"form":"liveset"}',
    });
    const { params } = presetQuery(preset, { viewMode: "sets" });
    const clusters = JSON.parse(params.clusters);

    expect(params.form).toBe("liveset");
    expect(params.year).toBe(2019);
    expect(clusters.some((c) => c.name === "YEAR")).toBe(false);
    expect(clusters).toContainEqual({ name: "LENGTH", value: "long" });
  });

  it("keeps several years as the cluster even with a form", () => {
    const preset = normalizePreset({
      id: 1,
      name: "x",
      params: '{"length":"long","year":["2019","2020"],"form":"liveset"}',
    });
    const { params } = presetQuery(preset, { viewMode: "sets" });

    expect(params.year).toBeUndefined();
    expect(JSON.parse(params.clusters)).toContainEqual({ name: "YEAR", value: ["2019", "2020"] });
  });

  it("sends neither form nor year for a preset without a form", () => {
    const preset = normalizePreset({
      id: 1,
      name: "x",
      params: '{"length":"long","year":["2019"]}',
    });
    const { params } = presetQuery(preset, { viewMode: "sets" });

    expect(params.form).toBeUndefined();
    expect(params.year).toBeUndefined();
  });

  it("the filter bar's Soort is saved with a preset from the sets view", () => {
    const params = JSON.parse(
      presetParamsFromFilters({ year: "2012", form: "liveset", viewMode: "sets" }),
    );
    expect(params).toMatchObject({ form: "liveset", year: ["2012"], length: "long" });
  });

  it("names the form in the tile's summary", () => {
    const preset = normalizePreset({
      id: 1,
      name: "x",
      params: '{"length":"long","form":"podcast"}',
    });
    expect(presetSummary(preset, (key) => key)).toContain("filter.form.podcast");
  });
});
