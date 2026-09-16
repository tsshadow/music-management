/**
 * The colours and covers behind the five daily-mix cards.
 *
 * The spectrum bands should draw a genre's own colour when the mix actually plays one, and a
 * fixed soft/mid/hard ramp otherwise; the rotating mixes should try the artist's photo and fall
 * back to a colour from the name. None of this should ever throw when MuMa is unreachable -- a
 * card with no data is still a card.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { hashColor, imageLoads, loadDailyMixCards } from "../../src/lib/dailyMixes.js";
import {
  DAILY_MIX_ARTIST,
  DAILY_MIX_HARD,
  DAILY_MIX_LABEL,
  DAILY_MIX_MID,
  DAILY_MIX_SOFT,
} from "../../src/lib/feeds.js";

vi.mock("../../src/lib/feeds.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    listFeeds: (...args) => globalThis.__listFeeds(...args),
    fetchFeed: (...args) => globalThis.__fetchFeed(...args),
  };
});

vi.mock("../../src/lib/mumaApi.js", () => ({
  apiBase: () => "http://muma",
}));

function trackOf(...genres) {
  return { genres };
}

describe("hashColor", () => {
  it("is stable for the same name", () => {
    expect(hashColor("Angerfist")).toBe(hashColor("Angerfist"));
  });

  it("differs for most names, so tiles do not all draw the same colour", () => {
    expect(hashColor("Angerfist")).not.toBe(hashColor("Rebelion"));
  });
});

describe("imageLoads", () => {
  const realImage = globalThis.Image;

  afterEach(() => {
    globalThis.Image = realImage;
  });

  it("resolves true when the image loads", async () => {
    globalThis.Image = class {
      set src(_url) {
        this.onload?.();
      }
    };

    expect(await imageLoads("https://muma.example/exists.jpg")).toBe(true);
  });

  it("resolves false when the image 404s", async () => {
    globalThis.Image = class {
      set src(_url) {
        this.onerror?.();
      }
    };

    expect(await imageLoads("https://muma.example/missing.jpg")).toBe(false);
  });
});

describe("loadDailyMixCards", () => {
  const AUTH = "u=user&p=secret&v=1.16.1&c=test&f=json";

  beforeEach(() => {
    globalThis.__listFeeds = vi.fn(async () => [
      { slug: DAILY_MIX_SOFT, title: "Zachter", subtitle: "≤ 42 hardheid" },
      { slug: DAILY_MIX_MID, title: "Middenin", subtitle: "42–70 hardheid" },
      { slug: DAILY_MIX_HARD, title: "Harder", subtitle: "≥ 70 hardheid" },
      { slug: DAILY_MIX_ARTIST, title: "Angerfist", subtitle: "Een artiest uit jouw top 10" },
      { slug: DAILY_MIX_LABEL, title: "Neophyte Records", subtitle: "Een label uit jouw top 10" },
    ]);
    globalThis.__fetchFeed = vi.fn(async () => ({ tracks: [] }));
    globalThis.Image = class {
      set src(_url) {
        this.onerror?.();
      }
    };
  });

  it("builds one card per mix, in soft/mid/hard/artist/label order", async () => {
    const cards = await loadDailyMixCards({}, AUTH);

    expect(cards.map((c) => c.slug)).toEqual([
      DAILY_MIX_SOFT,
      DAILY_MIX_MID,
      DAILY_MIX_HARD,
      DAILY_MIX_ARTIST,
      DAILY_MIX_LABEL,
    ]);
    expect(cards.map((c) => c.title)).toEqual([
      "Zachter",
      "Middenin",
      "Harder",
      "Angerfist",
      "Neophyte Records",
    ]);
  });

  it("colours a band by the ramp when its tracks carry no genre a tint answers for", async () => {
    const cards = await loadDailyMixCards({}, AUTH);
    const [soft, mid, hard] = cards;

    expect(soft.color).toBe("#1DB954");
    expect(mid.color).toBe("#2D5AFC");
    expect(hard.color).toBe("#E23744");
    expect(soft.cover).toBeNull();
  });

  it("colours a band by its own top genre's tint when one is known", async () => {
    globalThis.__fetchFeed = vi.fn(async (slug) =>
      slug === DAILY_MIX_SOFT
        ? { tracks: [trackOf("Euphoric Hardstyle"), trackOf("Euphoric Hardstyle")] }
        : { tracks: [] },
    );

    const cards = await loadDailyMixCards({ "euphoric hardstyle": "#FF00AA" }, AUTH);

    expect(cards[0].color).toBe("#FF00AA");
  });

  it("gives the artist card its photo when one loads", async () => {
    globalThis.Image = class {
      set src(_url) {
        this.onload?.();
      }
    };

    const cards = await loadDailyMixCards({}, AUTH);
    const artist = cards.find((c) => c.slug === DAILY_MIX_ARTIST);

    expect(artist.cover).toBe(
      `http://muma/api/artists/${encodeURIComponent("Angerfist")}/image?${AUTH}`,
    );
  });

  it("falls back to a name-based colour for the artist when there is no photo", async () => {
    const cards = await loadDailyMixCards({}, AUTH);
    const artist = cards.find((c) => c.slug === DAILY_MIX_ARTIST);

    expect(artist.cover).toBeNull();
    expect(artist.color).toBe(hashColor("Angerfist"));
  });

  it("never tries a photo for the label -- there is no label-image endpoint", async () => {
    const cards = await loadDailyMixCards({}, AUTH);
    const label = cards.find((c) => c.slug === DAILY_MIX_LABEL);

    expect(label.cover).toBeNull();
    expect(label.color).toBe(hashColor("Neophyte Records"));
  });

  it("still builds every card when MuMa never answers the list at all", async () => {
    globalThis.__listFeeds = vi.fn(async () => []);

    const cards = await loadDailyMixCards({}, AUTH);

    expect(cards).toHaveLength(5);
    expect(cards.every((c) => typeof c.color === "string")).toBe(true);
  });

  it("skips the artist-image check without credentials", async () => {
    const cards = await loadDailyMixCards({}, "");
    const artist = cards.find((c) => c.slug === DAILY_MIX_ARTIST);

    expect(artist.cover).toBeNull();
  });
});
