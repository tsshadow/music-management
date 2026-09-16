import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import Settings from "../../src/lib/Settings.svelte";
import SettingsSidebar from "../../src/lib/SettingsSidebar.svelte";
import { activeSettingsTab, credentials } from "../../src/lib/store.js";
import { platform } from "../../src/lib/platform/index.js";

function mockUser() {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({
      "subsonic-response": {
        status: "ok",
        user: { username: "user", adminRole: true, uiArtistReleaseSortMethod: 8 },
      },
    }),
  }));
}

describe("player settings navigation", () => {
  beforeEach(() => {
    globalThis.fetch = mockUser();
    credentials.set({ url: "", username: "user", password: "pw" });
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
    expect(screen.getByText("Algemene Instellingen")).toBeTruthy();
  });
});
