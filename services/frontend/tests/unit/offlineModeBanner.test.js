import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/svelte";
import { tick } from "svelte";
import { get } from "svelte/store";
import OfflineModeBanner from "../../src/lib/OfflineModeBanner.svelte";
import { offlineMode } from "../../src/lib/offlineMode.js";
import { t } from "../../src/lib/i18n/index.js";

/** The strip that marks the whole app as the device's own copy after "Offline verder". */
describe("OfflineModeBanner", () => {
  beforeEach(() => {
    offlineMode.set({
      active: false,
      since: null,
      skipped: 0,
      restored: 0,
      returnedAt: null,
      restoredOnReturn: 0,
    });
  });

  it("is absent while the app is online", () => {
    render(OfflineModeBanner);
    expect(screen.queryByTestId("offline-mode-banner")).toBeNull();
  });

  it("says the app is offline and how many queued tracks were left out", async () => {
    render(OfflineModeBanner);
    offlineMode.set({
      active: true,
      since: 1,
      skipped: 12,
      restored: 3,
      returnedAt: null,
      restoredOnReturn: 0,
    });
    await tick();

    expect(screen.getByTestId("offline-mode-banner")).toHaveTextContent(
      get(t)("offlineMode.banner"),
    );
    expect(screen.getByTestId("offline-mode-skipped")).toHaveTextContent(
      get(t)("offlineMode.skipped", { count: 12 }),
    );
    expect(screen.getByTestId("offline-mode-reconnect")).toBeEnabled();
  });

  it("leaves the count out when every queued track was on the device", async () => {
    render(OfflineModeBanner);
    offlineMode.set({
      active: true,
      since: 1,
      skipped: 0,
      restored: 3,
      returnedAt: null,
      restoredOnReturn: 0,
    });
    await tick();
    expect(screen.queryByTestId("offline-mode-skipped")).toBeNull();
  });
});
