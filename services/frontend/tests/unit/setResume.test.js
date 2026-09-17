import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mumaUser, mumaApiKey, mumaApiUrl } from "../../src/lib/store.js";
import {
  SET_RESUME_KEY,
  MAX_SET_RESUME_ENTRIES,
  RESUME_MIN_SECONDS,
  RESUME_END_MARGIN_SECONDS,
  resumeKeyFor,
  shouldResume,
  loadSetResumePositions,
  saveSetResumePosition,
} from "../../src/lib/setResume.js";

function fetchReturning(settings) {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({ settings: settings === undefined ? undefined : JSON.stringify(settings) }),
  }));
}

describe("resumeKeyFor", () => {
  it("keys a grouped track on its work id, the same as the song page", () => {
    expect(resumeKeyFor({ id: "1", workId: 42 })).toBe("work:42");
  });

  it("falls back to the track id for an ungrouped file", () => {
    expect(resumeKeyFor({ id: "9" })).toBe("track:9");
    expect(resumeKeyFor({ id: "9", workId: 0 })).toBe("track:9");
  });
});

describe("shouldResume", () => {
  it("is false for nothing stored", () => {
    expect(shouldResume(null, 7200)).toBe(false);
    expect(shouldResume(undefined, 7200)).toBe(false);
  });

  it("is false just short of the minimum, true at it", () => {
    expect(shouldResume({ position: RESUME_MIN_SECONDS - 1 }, 7200)).toBe(false);
    expect(shouldResume({ position: RESUME_MIN_SECONDS }, 7200)).toBe(true);
  });

  it("is false within the last minute of a known duration", () => {
    const duration = 7200;
    expect(shouldResume({ position: duration - RESUME_END_MARGIN_SECONDS + 1 }, duration)).toBe(
      false,
    );
    expect(shouldResume({ position: duration - RESUME_END_MARGIN_SECONDS }, duration)).toBe(true);
  });

  it("does not gate on the end margin when the duration is unknown", () => {
    expect(shouldResume({ position: 3600 }, 0)).toBe(true);
  });
});

describe("loadSetResumePositions / saveSetResumePosition", () => {
  beforeEach(() => {
    mumaUser.set({ id: 7 });
    mumaApiKey.set("test-key");
    mumaApiUrl.set("https://muma.test");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    mumaUser.set(null);
  });

  it("is empty with nobody signed in", async () => {
    mumaUser.set(null);
    global.fetch = vi.fn();

    expect(await loadSetResumePositions()).toEqual({});
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("reads the stored map back out of the account blob", async () => {
    global.fetch = fetchReturning({ setResume: { "work:1": { position: 120, updatedAt: 1 } } });

    expect(await loadSetResumePositions()).toEqual({ "work:1": { position: 120, updatedAt: 1 } });
  });

  it("is empty when the account has never written the key", async () => {
    global.fetch = fetchReturning({ favoriteGenres: [] });

    expect(await loadSetResumePositions()).toEqual({});
  });

  it("merges one set's position into whatever the account already has", async () => {
    let saved = null;
    global.fetch = vi.fn(async (url, options) => {
      if (!options?.body) {
        return {
          ok: true,
          json: async () => ({
            settings: JSON.stringify({ setResume: { "work:1": { position: 10, updatedAt: 1 } } }),
          }),
        };
      }
      saved = JSON.parse(JSON.parse(options.body).settings);
      return { ok: true, json: async () => ({}) };
    });

    await saveSetResumePosition("work:2", 305);

    expect(saved.setResume["work:1"]).toEqual({ position: 10, updatedAt: 1 });
    expect(saved.setResume["work:2"].position).toBe(305);
    expect(typeof saved.setResume["work:2"].updatedAt).toBe("number");
  });

  it("never stores a position of zero or less", async () => {
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));

    await saveSetResumePosition("work:1", 0);
    await saveSetResumePosition("work:1", -5);
    await saveSetResumePosition("work:1", NaN);

    // Counted by content rather than by call: signing in above also arms the
    // store's own debounced account saves (the language, for one), and which
    // test those land in depends on nothing this test controls.
    const stored = global.fetch.mock.calls
      .filter(([, options]) => options?.body)
      .map(([, options]) => JSON.parse(JSON.parse(options.body).settings)[SET_RESUME_KEY] ?? {});
    const positions = stored.flatMap((map) => Object.values(map).map((entry) => entry.position));
    expect(positions.every((position) => position > 0)).toBe(true);
  });

  it("caps the stored map to the most recently updated entries", async () => {
    const many = {};
    for (let i = 0; i < MAX_SET_RESUME_ENTRIES; i++) {
      many[`work:${i}`] = { position: 100, updatedAt: i };
    }
    let saved = null;
    global.fetch = vi.fn(async (url, options) => {
      if (!options?.body) {
        return { ok: true, json: async () => ({ settings: JSON.stringify({ setResume: many }) }) };
      }
      saved = JSON.parse(JSON.parse(options.body).settings);
      return { ok: true, json: async () => ({}) };
    });

    // A brand new set, more recent than everything already stored.
    await saveSetResumePosition("work:new", 400);

    const keys = Object.keys(saved.setResume);
    expect(keys.length).toBe(MAX_SET_RESUME_ENTRIES);
    expect(keys).toContain("work:new");
    // The oldest (updatedAt: 0) is the one that had to make room.
    expect(keys).not.toContain("work:0");
  });
});

describe("SET_RESUME_KEY", () => {
  it("is the key the account settings blob stores this under", () => {
    expect(SET_RESUME_KEY).toBe("setResume");
  });
});
