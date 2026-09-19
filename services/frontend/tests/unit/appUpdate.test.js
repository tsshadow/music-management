import { beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";

import {
  CHECK_INTERVAL_MS,
  STORAGE_KEY,
  checkForAppUpdate,
  isCheckDue,
  isOtherSeries,
} from "../../src/lib/appUpdate.js";
import { dismissAll, notifications } from "../../src/lib/notifications.js";

/** A storage the way `localStorage` behaves, without the browser. */
function memoryStorage(entries = {}) {
  const map = new Map(Object.entries(entries));
  return {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    map,
  };
}

const NEWER = {
  available: true,
  currentVersionCode: 312,
  currentVersionName: "6.36.0",
  currentSeries: "muma-mobile",
  latestVersionCode: 313,
  latestVersionName: "6.36.0",
  latestSeries: "muma-mobile",
  url: "https://apk.example/dl/313?u=guest&p=guest",
};

const SAME = { ...NEWER, available: false, latestVersionCode: 312 };

/** A debug phone on 7.0.0 (316) while the release series went on to 7.3.0 (320). */
const RELEASE_AHEAD = {
  available: true,
  currentVersionCode: 316,
  currentVersionName: "7.0.0",
  currentSeries: "muma-mobile-debug",
  latestVersionCode: 320,
  latestVersionName: "7.3.0",
  latestSeries: "muma-mobile",
  url: "https://apk.example/dl/320?u=guest&p=guest",
};

function nativePlatform(answer) {
  return {
    system: {
      isNative: true,
      checkForUpdate: vi.fn(typeof answer === "function" ? answer : async () => answer),
      openUrl: vi.fn(async () => {}),
    },
  };
}

describe("isCheckDue", () => {
  it("is due when nothing was ever stored, or the storage is missing", () => {
    expect(isCheckDue(memoryStorage(), 1_000)).toBe(true);
    expect(isCheckDue(null, 1_000)).toBe(true);
  });

  it("holds for a day after the last answer and is due again after", () => {
    const storage = memoryStorage({ [STORAGE_KEY]: "1000" });
    expect(isCheckDue(storage, 1000 + CHECK_INTERVAL_MS - 1)).toBe(false);
    expect(isCheckDue(storage, 1000 + CHECK_INTERVAL_MS)).toBe(true);
  });

  it("treats a garbled timestamp as never checked", () => {
    expect(isCheckDue(memoryStorage({ [STORAGE_KEY]: "yesterday" }), 5)).toBe(true);
  });
});

describe("checkForAppUpdate", () => {
  beforeEach(() => {
    dismissAll();
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  it("never asks in a browser tab", async () => {
    const platform = { system: { isNative: false, checkForUpdate: vi.fn() } };

    expect(await checkForAppUpdate({ platform, storage: memoryStorage() })).toBeNull();
    expect(platform.system.checkForUpdate).not.toHaveBeenCalled();
  });

  it("announces a newer build with a download action that goes to the shell", async () => {
    const platform = nativePlatform(NEWER);
    const storage = memoryStorage();

    const update = await checkForAppUpdate({ platform, storage, now: 5_000 });

    expect(update).toEqual(NEWER);
    const [toast] = get(notifications);
    expect(toast.type).toBe("info");
    expect(toast.message).toContain("6.36.0");
    expect(toast.action.label).toBe("Downloaden");
    toast.action.onClick();
    expect(platform.system.openUrl).toHaveBeenCalledWith(NEWER.url);
    expect(storage.getItem(STORAGE_KEY)).toBe("5000");
  });

  // The debug series only moves when somebody runs the manual build job, so the shell asks
  // after the release series too; that APK installs beside the debug one, so the toast must
  // not promise an "update" -- it says the release is ahead, and still hands over the download.
  it("words a release that outran a debug build as that, with the release download", async () => {
    const platform = nativePlatform(RELEASE_AHEAD);

    await checkForAppUpdate({ platform, storage: memoryStorage() });

    const [toast] = get(notifications);
    expect(toast.type).toBe("info");
    expect(toast.message).toBe("Deze debug-build (7.0.0) is ouder dan release 7.3.0.");
    toast.action.onClick();
    expect(platform.system.openUrl).toHaveBeenCalledWith(RELEASE_AHEAD.url);
  });

  it("only calls it another series when the shell named one", () => {
    expect(isOtherSeries(RELEASE_AHEAD)).toBe(true);
    expect(isOtherSeries(NEWER)).toBe(false);
    // An older shell that does not report series yet reads as the plain "new version".
    expect(isOtherSeries({ ...NEWER, currentSeries: "", latestSeries: "" })).toBe(false);
  });

  it("stays quiet on an automatic check that finds nothing", async () => {
    const platform = nativePlatform(SAME);

    await checkForAppUpdate({ platform, storage: memoryStorage() });

    expect(get(notifications)).toHaveLength(0);
  });

  it("skips an automatic check that is not due yet, but never a manual one", async () => {
    const platform = nativePlatform(SAME);
    const storage = memoryStorage({ [STORAGE_KEY]: "1000" });

    expect(await checkForAppUpdate({ platform, storage, now: 2000 })).toBeNull();
    expect(platform.system.checkForUpdate).not.toHaveBeenCalled();

    expect(await checkForAppUpdate({ platform, storage, now: 2000, manual: true })).toEqual(SAME);
    expect(platform.system.checkForUpdate).toHaveBeenCalledTimes(1);
  });

  it("tells a listener who pressed the button that they are up to date", async () => {
    await checkForAppUpdate({
      platform: nativePlatform(SAME),
      storage: memoryStorage(),
      manual: true,
    });

    const [toast] = get(notifications);
    expect(toast.type).toBe("success");
    expect(toast.message).toContain("6.36.0");
  });

  // "Could not check" and "up to date" are different answers; a failed check must never
  // read as the second, and must not push the next automatic check a day out either.
  it("reports a failed manual check as a failure and leaves the timestamp alone", async () => {
    const platform = nativePlatform(async () => {
      throw new Error("update check failed: apk-hoster answered 503");
    });
    const storage = memoryStorage();

    expect(await checkForAppUpdate({ platform, storage, manual: true })).toBeNull();

    const [toast] = get(notifications);
    expect(toast.type).toBe("error");
    expect(toast.detail).toContain("503");
    expect(storage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("swallows a failed automatic check without a word", async () => {
    const platform = nativePlatform(async () => {
      throw new Error("offline");
    });

    expect(await checkForAppUpdate({ platform, storage: memoryStorage() })).toBeNull();
    expect(get(notifications)).toHaveLength(0);
  });
});
