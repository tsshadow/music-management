import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import Settings from "../../src/lib/Settings.svelte";
import SettingsSidebar from "../../src/lib/SettingsSidebar.svelte";
import { activeSettingsTab, credentials } from "../../src/lib/store.js";
import { platform } from "../../src/lib/platform/index.js";
import { t } from "../../src/lib/i18n/index.js";
import { settingsTabs } from "../../src/lib/lazyViews.js";
import { LAZY_HOOK_TIMEOUT_MS, loadSettingsTab, lazyWait } from "./lazyTestUtils.js";

// The settings tabs are separate chunks (issue #119). General is loaded before the tests, so the
// ones about what it shows render it on the first frame (issue #120).
beforeAll(() => loadSettingsTab("general"), LAZY_HOOK_TIMEOUT_MS);

/** A promise with its resolve/reject handed out, to hold a chunk "on its way". */
function deferred() {
  let resolve;
  const promise = new Promise((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function mockUser() {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({
      "subsonic-response": {
        status: "ok",
        user: { username: "demo-user", adminRole: true, uiArtistReleaseSortMethod: 8 },
      },
    }),
  }));
}

describe("player settings navigation", () => {
  beforeEach(() => {
    globalThis.fetch = mockUser();
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    activeSettingsTab.set("general");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("only offers the personal tabs -- server administration lives in the management view", () => {
    render(SettingsSidebar, { onnavigate: () => {} });

    expect(screen.getByText("Algemeen")).toBeTruthy();
    expect(screen.getByText("Geavanceerd")).toBeTruthy();
    expect(screen.getByText("Over")).toBeTruthy();
    expect(screen.getByText("Handleiding")).toBeTruthy();

    for (const gone of ["Bibliotheken", "Scan Instellingen", "Scanner", "Gebruikers"]) {
      expect(screen.queryByText(gone)).toBeNull();
    }
  });

  // The whitelist behind it is a Kotlin plugin; there is nothing for the tab to open in
  // a browser tab, so it stays off `platform.system.isNative` the same way the Downloads
  // screen stays off `platform.storage.supported`.
  it("hides the device tab outside a native shell", () => {
    render(SettingsSidebar, { onnavigate: () => {} });

    expect(screen.queryByText("Apparaat")).toBeNull();
  });

  it("offers the device tab inside a native shell", () => {
    platform.system.isNative = true;
    try {
      render(SettingsSidebar, { onnavigate: () => {} });

      expect(screen.getByText("Apparaat")).toBeTruthy();
    } finally {
      platform.system.isNative = false;
    }
  });

  it("falls back to the general tab when a removed admin tab is still persisted", async () => {
    // An account that last had "scanner" open would otherwise land on a blank screen.
    activeSettingsTab.set("scanner");

    render(Settings);

    await waitFor(() => expect(get(activeSettingsTab)).toBe("general"));
    // General is loaded up front (beforeAll), so it is on screen as soon as the tab is.
    expect(screen.getByText("Algemene Instellingen")).toBeTruthy();
  });

  describe("each tab is its own chunk (issue #119)", () => {
    it("shows a form-shaped skeleton while the tab loads, then the tab", async () => {
      const Advanced = await settingsTabs.load("advanced");
      const held = deferred();
      const peek = settingsTabs.peek.bind(settingsTabs);
      const load = settingsTabs.load.bind(settingsTabs);
      vi.spyOn(settingsTabs, "peek").mockImplementation((name) =>
        name === "advanced" ? null : peek(name),
      );
      vi.spyOn(settingsTabs, "load").mockImplementation((name) =>
        name === "advanced" ? held.promise : load(name),
      );
      activeSettingsTab.set("advanced");

      render(Settings);

      expect(screen.getByTestId("settings-tab-loading")).toBeTruthy();
      expect(screen.queryByText(get(t)("settings.advanced.title"))).toBeNull();

      held.resolve(Advanced);

      expect(await screen.findByText(get(t)("settings.advanced.title"))).toBeTruthy();
      expect(screen.queryByTestId("settings-tab-loading")).toBeNull();
    });

    it("renders a tab that is already in on the first frame", () => {
      render(Settings);

      expect(screen.queryByTestId("settings-tab-loading")).toBeNull();
      expect(screen.getByText("Algemene Instellingen")).toBeTruthy();
    });

    it("fetches the next tab in the sidebar once the page is idle", async () => {
      const idle = vi.fn((cb) => setTimeout(cb, 0));
      vi.stubGlobal("requestIdleCallback", idle);
      // Advanced may already be in from an earlier test; the preload only runs for a tab that
      // is not, so report it as missing.
      const peek = settingsTabs.peek.bind(settingsTabs);
      vi.spyOn(settingsTabs, "peek").mockImplementation((name) =>
        name === "advanced" ? null : peek(name),
      );
      const loadSpy = vi.spyOn(settingsTabs, "load");
      try {
        render(Settings);

        await waitFor(() => expect(loadSpy).toHaveBeenCalledWith("advanced"), lazyWait);
        expect(idle).toHaveBeenCalled();
      } finally {
        vi.unstubAllGlobals();
      }
    });

    it("starts a tab's fetch when a finger goes down on it in the sidebar", async () => {
      const loadSpy = vi.spyOn(settingsTabs, "load").mockResolvedValue(null);
      render(SettingsSidebar, { onnavigate: () => {} });

      await fireEvent.pointerDown(screen.getByText("Over"));

      expect(loadSpy).toHaveBeenCalledWith("about");
      expect(get(activeSettingsTab)).toBe("general");
    });
  });
});
