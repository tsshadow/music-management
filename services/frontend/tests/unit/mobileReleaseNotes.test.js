import { describe, it, expect, vi, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  parseMobileChangelog,
  isNewerVersion,
  releasesSince,
  checkForMobileUpdate,
} from "../../src/lib/mobileReleaseNotes.js";
import { activeModal } from "../../src/lib/store.js";

const SAMPLE = `# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [6.35.1] - 2026-09-11

### Fixed
- **"Hoog gewaardeerd" was altijd leeg.** De sectie vroeg de server om nummers met
  een rating, en kreeg niets terug.

## [6.35.0] - 2026-09-11

### Added
- Het startscherm is nu van jou.
- Recent uitgebracht stond er weer bij.

### Changed
- Een ster is groen in de Spotify-stijl.

## [6.34.0] - 2026-09-11

### Added
- Dagelijkse mix staat nu ook op het startscherm.
`;

describe("parseMobileChangelog", () => {
  it("skips the Unreleased heading", () => {
    const releases = parseMobileChangelog(SAMPLE);

    expect(releases.some((r) => r.version.toLowerCase() === "unreleased")).toBe(false);
  });

  it("reads every released version, in the file's own order", () => {
    const releases = parseMobileChangelog(SAMPLE);

    expect(releases.map((r) => r.version)).toEqual(["6.35.1", "6.35.0", "6.34.0"]);
    expect(releases[0].date).toBe("2026-09-11");
  });

  it("groups bullets under their category", () => {
    const releases = parseMobileChangelog(SAMPLE);
    const v35 = releases.find((r) => r.version === "6.35.0");

    expect(v35.notes.Added).toEqual([
      "Het startscherm is nu van jou.",
      "Recent uitgebracht stond er weer bij.",
    ]);
    expect(v35.notes.Changed).toEqual(["Een ster is groen in de Spotify-stijl."]);
  });

  it("folds a wrapped bullet's continuation line into the same item", () => {
    const releases = parseMobileChangelog(SAMPLE);
    const v3511 = releases.find((r) => r.version === "6.35.1");

    expect(v3511.notes.Fixed).toEqual([
      '"Hoog gewaardeerd" was altijd leeg. De sectie vroeg de server om nummers met een rating, en kreeg niets terug.',
    ]);
  });

  it("strips markdown bold markers, since the modal renders plain text", () => {
    const releases = parseMobileChangelog(SAMPLE);
    const v3511 = releases.find((r) => r.version === "6.35.1");

    expect(v3511.notes.Fixed[0]).not.toContain("**");
  });

  it("returns nothing for an empty or missing changelog", () => {
    expect(parseMobileChangelog("")).toEqual([]);
    expect(parseMobileChangelog(undefined)).toEqual([]);
  });
});

describe("isNewerVersion", () => {
  it("compares dot-separated numeric parts", () => {
    expect(isNewerVersion("6.35.1", "6.35.0")).toBe(true);
    expect(isNewerVersion("6.35.0", "6.35.1")).toBe(false);
    expect(isNewerVersion("7.0.0", "6.35.1")).toBe(true);
    expect(isNewerVersion("6.35.0", "6.35.0")).toBe(false);
  });

  it("treats a shorter version as padded with zeros", () => {
    expect(isNewerVersion("6.35", "6.35.0")).toBe(false);
    expect(isNewerVersion("6.35.1", "6.35")).toBe(true);
  });
});

describe("releasesSince", () => {
  const releases = parseMobileChangelog(SAMPLE);

  it("keeps only the versions newer than what the device last saw", () => {
    expect(releasesSince("6.35.0", releases).map((r) => r.version)).toEqual(["6.35.1"]);
    expect(releasesSince("6.34.0", releases).map((r) => r.version)).toEqual(["6.35.1", "6.35.0"]);
  });

  it("keeps everything when the device is far behind", () => {
    expect(releasesSince("1.0.0", releases)).toHaveLength(3);
  });
});

describe("checkForMobileUpdate", () => {
  function fakeStorage(initial = {}) {
    const data = { ...initial };
    return {
      getItem: (key) => data[key] ?? null,
      setItem: (key, value) => {
        data[key] = value;
      },
      _data: data,
    };
  }

  afterEach(() => {
    activeModal.set(null);
  });

  it("does nothing in a browser tab", async () => {
    const platform = { system: { isNative: false, appVersion: vi.fn() } };
    const storage = fakeStorage();

    await checkForMobileUpdate({ platform, storage });

    expect(platform.system.appVersion).not.toHaveBeenCalled();
    expect(get(activeModal)).toBeNull();
  });

  it("remembers the version on a first install without showing anything", async () => {
    const platform = {
      system: { isNative: true, appVersion: vi.fn().mockResolvedValue("6.35.1") },
    };
    const storage = fakeStorage();

    await checkForMobileUpdate({ platform, storage });

    expect(storage.getItem("muma_mobile_last_app_version")).toBe("6.35.1");
    expect(get(activeModal)).toBeNull();
  });

  it("shows what changed since the version the device last saw", async () => {
    const platform = {
      system: {
        isNative: true,
        appVersion: vi.fn().mockResolvedValue("6.35.1"),
        releaseNotes: vi.fn().mockResolvedValue(SAMPLE),
      },
    };
    const storage = fakeStorage({ muma_mobile_last_app_version: "6.34.0" });

    await checkForMobileUpdate({ platform, storage });

    const modal = get(activeModal);
    expect(modal.type).toBe("release-notes");
    expect(modal.data.releases.map((r) => r.version)).toContain("6.35.1");
    expect(storage.getItem("muma_mobile_last_app_version")).toBe("6.35.1");
  });

  it("shows nothing when the version has not actually changed", async () => {
    const platform = {
      system: {
        isNative: true,
        appVersion: vi.fn().mockResolvedValue("6.35.1"),
        releaseNotes: vi.fn(),
      },
    };
    const storage = fakeStorage({ muma_mobile_last_app_version: "6.35.1" });

    await checkForMobileUpdate({ platform, storage });

    expect(platform.system.releaseNotes).not.toHaveBeenCalled();
    expect(get(activeModal)).toBeNull();
  });

  it("shows nothing when the shell has no changelog asset to read", async () => {
    const platform = {
      system: {
        isNative: true,
        appVersion: vi.fn().mockResolvedValue("6.35.1"),
        releaseNotes: vi.fn().mockResolvedValue(null),
      },
    };
    const storage = fakeStorage({ muma_mobile_last_app_version: "6.34.0" });

    await checkForMobileUpdate({ platform, storage });

    expect(get(activeModal)).toBeNull();
  });

  it("resolves without throwing when the appVersion bridge call fails", async () => {
    const platform = {
      system: { isNative: true, appVersion: vi.fn().mockRejectedValue(new Error("no bridge")) },
    };
    const storage = fakeStorage();

    await expect(checkForMobileUpdate({ platform, storage })).resolves.toBeUndefined();
    expect(get(activeModal)).toBeNull();
  });

  it("resolves without throwing when the releaseNotes bridge call fails", async () => {
    const platform = {
      system: {
        isNative: true,
        appVersion: vi.fn().mockResolvedValue("6.35.1"),
        releaseNotes: vi.fn().mockRejectedValue(new Error("no bridge")),
      },
    };
    const storage = fakeStorage({ muma_mobile_last_app_version: "6.34.0" });

    await expect(checkForMobileUpdate({ platform, storage })).resolves.toBeUndefined();
    expect(get(activeModal)).toBeNull();
  });
});
