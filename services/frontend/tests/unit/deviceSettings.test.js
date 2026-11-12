import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/svelte";
import DeviceSettings from "../../src/lib/settings/DeviceSettings.svelte";
import { platform } from "../../src/lib/platform/index.js";

/**
 * `platform` resolves to the browser implementation in this test environment, so every
 * native-only member `DeviceSettings.svelte` calls is stubbed directly on the shared
 * singleton for the duration of each test -- the same trick `loginPageNativeCredentials.test.js`
 * uses for `isNative`, extended to the methods this component actually calls: `getSettings`,
 * `setSetting`, `storage.clearCache`, `diagnostics.send`,
 * `listBondedDevices`, `requestCarModeFullScreenPermission`, `pickCacheLocation` and
 * `clearCustomCacheLocation`. In the real native shell these all come from the Capacitor
 * plugins; here they are plain mocks, because the point of these tests is what the component
 * does with the answers, not the bridge itself -- that is `platformCapacitor.test.js`'s job.
 */
function baseSettings(overrides = {}) {
  return {
    wifiOnly: false,
    parallelDownloads: 3,
    cacheSizeMB: 5000,
    cacheLocationUri: "",
    customCacheLocation: false,
    maxBitrateMobile: 128,
    maxBitrateWifi: 0,
    maxBitratePinning: 320,
    preloadCount: 5,
    resumeOnHeadphonesPlug: false,
    resumeOnBluetoothDevice: 0,
    pauseOnBluetoothDevice: 1,
    hardwareOffload: false,
    carModeManual: false,
    carModeDevices: [],
    networkTimeout: 60000,
    autoSwitchOffline: false,
    directoryCacheTime: 300,
    hideMedia: false,
    mediaDeviceExport: false,
    scrobbleEnabled: true,
    mumaApiKeySet: false,
    ...overrides,
  };
}

describe("DeviceSettings", () => {
  beforeEach(() => {
    platform.system.getSettings = vi.fn(async () => baseSettings());
    platform.system.setSetting = vi.fn(async () => {});
    platform.system.listBondedDevices = vi.fn(async () => ({
      permissionGranted: true,
      devices: [],
    }));
    platform.system.requestCarModeFullScreenPermission = vi.fn();
    platform.system.pickCacheLocation = vi.fn(async () => ({}));
    platform.system.clearCustomCacheLocation = vi.fn(async () => {});
    platform.storage.clearCache = vi.fn(async () => {});
    platform.diagnostics.send = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the rows from what getSettings answered", async () => {
    render(DeviceSettings);

    await waitFor(() => expect(screen.getByText("Downloads")).toBeInTheDocument());
    expect(screen.getByText("Streaming")).toBeInTheDocument();
    expect(screen.getByText("Afspelen")).toBeInTheDocument();
    expect(screen.getByText("Auto")).toBeInTheDocument();
    expect(screen.getByText("Diagnostiek")).toBeInTheDocument();
    expect(screen.getByLabelText("Alleen wifi")).not.toBeChecked();
    expect(screen.getByText("Geen apparaten gekoppeld")).toBeInTheDocument();
  });

  it("shows how many car-mode devices are paired, pluralised", async () => {
    platform.system.getSettings = vi.fn(async () =>
      baseSettings({ carModeDevices: ["AA:BB:CC", "DD:EE:FF"] }),
    );

    render(DeviceSettings);

    await waitFor(() => expect(screen.getByText("2 apparaten gekoppeld")).toBeInTheDocument());
  });

  it("opens the device picker pre-ticking what carModeDevices already holds", async () => {
    platform.system.getSettings = vi.fn(async () => baseSettings({ carModeDevices: ["AA:BB:CC"] }));
    platform.system.listBondedDevices = vi.fn(async () => ({
      permissionGranted: true,
      devices: [
        { address: "AA:BB:CC", name: "Car Kit", isCarClass: true },
        { address: "11:22:33", name: "Earbuds", isCarClass: false },
      ],
    }));

    render(DeviceSettings);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Bewerken…" })).toBeInTheDocument(),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Bewerken…" }));

    await waitFor(() => expect(screen.getByText("Car Kit")).toBeInTheDocument());
    expect(screen.getByLabelText("Car Kit")).toBeChecked();
    expect(screen.getByLabelText("Earbuds")).not.toBeChecked();

    await fireEvent.click(screen.getByLabelText("Earbuds"));
    await fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));

    expect(platform.system.setSetting).toHaveBeenCalledWith({
      key: "carModeDevices",
      value: ["AA:BB:CC", "11:22:33"],
    });
  });

  it("requesting the full-screen permission calls the platform action", async () => {
    platform.system.getSettings = vi.fn(async () =>
      baseSettings({ carModeFullScreenGranted: false }),
    );

    render(DeviceSettings);
    await waitFor(() => expect(screen.getByText("Toestaan…")).toBeInTheDocument());

    await fireEvent.click(screen.getByText("Toestaan…"));

    expect(platform.system.requestCarModeFullScreenPermission).toHaveBeenCalled();
  });

  it("picking a cache location updates the shown path", async () => {
    platform.system.pickCacheLocation = vi.fn(async () => ({
      uri: "content://tree/abc",
      path: "/tree/abc",
    }));

    render(DeviceSettings);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Kies map…" })).toBeInTheDocument(),
    );

    await fireEvent.click(screen.getByRole("button", { name: "Kies map…" }));

    await waitFor(() => expect(screen.getByText("/tree/abc")).toBeInTheDocument());
  });

  it("shows the muma sync fields as read-only", async () => {
    platform.system.getSettings = vi.fn(async () =>
      baseSettings({ mumaUserId: 42, mumaApiKeySet: true }),
    );

    render(DeviceSettings);

    await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
    expect(screen.getByText("Gekoppeld")).toBeInTheDocument();
  });

  it("hides the full-screen row when getSettings left it out entirely", async () => {
    render(DeviceSettings);

    await waitFor(() => expect(screen.getByText("Downloads")).toBeInTheDocument());
    expect(screen.queryByText("Scherm automatisch aanzetten")).toBeNull();
  });

  it("shows the full-screen row and an action button when the permission is missing", async () => {
    platform.system.getSettings = vi.fn(async () =>
      baseSettings({ carModeFullScreenGranted: false }),
    );

    render(DeviceSettings);

    await waitFor(() =>
      expect(screen.getByText("Scherm automatisch aanzetten")).toBeInTheDocument(),
    );
    expect(screen.getByText("Niet toegestaan")).toBeInTheDocument();
    expect(screen.getByText("Toestaan…")).toBeInTheDocument();
  });

  it("toggling a switch writes the setting through platform.system.setSetting", async () => {
    render(DeviceSettings);
    await waitFor(() => expect(screen.getByLabelText("Alleen wifi")).toBeInTheDocument());

    await fireEvent.click(screen.getByLabelText("Alleen wifi"));

    expect(platform.system.setSetting).toHaveBeenCalledWith({ key: "wifiOnly", value: true });
  });

  it("switches the floating player on leave through setSetting", async () => {
    render(DeviceSettings);
    const toggle = await screen.findByLabelText("Zwevende speler bij verlaten");

    await fireEvent.click(toggle);

    expect(platform.system.setSetting).toHaveBeenCalledWith({ key: "pipOnLeave", value: true });
  });

  it("rolls a toggle back and shows an error when the write is rejected", async () => {
    platform.system.setSetting = vi.fn(async () => {
      throw new Error("rejected: unknown setting");
    });
    render(DeviceSettings);
    await waitFor(() => expect(screen.getByLabelText("Alleen wifi")).toBeInTheDocument());

    await fireEvent.click(screen.getByLabelText("Alleen wifi"));

    await waitFor(() => expect(screen.getByLabelText("Alleen wifi")).not.toBeChecked());
    expect(screen.getByText("Kon die instelling niet opslaan.")).toBeInTheDocument();
  });

  it("changing a select writes the numeric value", async () => {
    render(DeviceSettings);
    await waitFor(() =>
      expect(screen.getByLabelText("Gelijktijdige downloads")).toBeInTheDocument(),
    );

    await fireEvent.change(screen.getByLabelText("Gelijktijdige downloads"), {
      target: { value: "5" },
    });

    expect(platform.system.setSetting).toHaveBeenCalledWith({ key: "parallelDownloads", value: 5 });
  });

  it("clearing the cache calls platform.storage.clearCache", async () => {
    render(DeviceSettings);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Cache wissen" })).toBeInTheDocument(),
    );

    await fireEvent.click(screen.getByRole("button", { name: "Cache wissen" }));

    await waitFor(() => expect(platform.storage.clearCache).toHaveBeenCalled());
    expect(screen.getByText("Cache gewist.")).toBeInTheDocument();
  });

  it("sending diagnostics calls platform.diagnostics.send", async () => {
    render(DeviceSettings);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Diagnostiek nu versturen" })).toBeInTheDocument(),
    );

    await fireEvent.click(screen.getByRole("button", { name: "Diagnostiek nu versturen" }));

    expect(platform.diagnostics.send).toHaveBeenCalled();
    expect(screen.getByText("Diagnostiek verstuurd.")).toBeInTheDocument();
  });

  it("shows a load error rather than a blank page when getSettings rejects", async () => {
    platform.system.getSettings = vi.fn(async () => {
      throw new Error("bridge not ready");
    });

    render(DeviceSettings);

    await waitFor(() =>
      expect(screen.getByText("Kon de apparaatinstellingen niet laden.")).toBeInTheDocument(),
    );
  });
});
