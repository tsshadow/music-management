import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/svelte";
import DeviceSettings from "../../src/lib/settings/DeviceSettings.svelte";
import { platform } from "../../src/lib/platform/index.js";
import { credentials } from "../../src/lib/store.js";
import { switchServer } from "../../src/lib/serverAddress.js";

vi.mock("../../src/lib/serverAddress.js", async (importOriginal) => ({
  ...(await importOriginal()),
  switchServer: vi.fn(async () => {}),
}));

/**
 * The "Server" row of Settings > Apparaat (issue #192): it shows the address in use, opens the
 * first-run screen to change it, keeps the session for another spelling of the same server and
 * asks first for another server. `platform` is the browser singleton with the native members
 * stubbed, as in `deviceSettings.test.js`.
 */
describe("DeviceSettings server row", () => {
  beforeEach(() => {
    credentials.set({ url: "https://music.example.org", username: "demo-user" });
    platform.system.getSettings = vi.fn(async () => ({ carModeDevices: [] }));
    platform.system.suggestedServerAddress = vi.fn(async () => "");
    platform.system.setServerAddress = vi.fn(async () => {});
    platform.system.loadServerUrl = vi.fn(async () => ({
      subsonic: "https://music.example.org",
      mumaApi: "https://music.example.org/muma",
      configured: true,
    }));
    vi.mocked(switchServer).mockClear();
  });

  afterEach(() => {
    delete platform.system.loadServerUrl;
    vi.restoreAllMocks();
  });

  async function openChange(answerUrl) {
    platform.system.checkServerAddress = vi.fn(async () => ({
      state: "ok",
      url: answerUrl,
      subsonic: answerUrl,
      mumaApi: `${answerUrl}/muma`,
      buildServer: false,
    }));
    render(DeviceSettings);
    await waitFor(() => expect(screen.getByTestId("device-server")).toBeInTheDocument());
    expect(screen.getByTestId("device-server").textContent).toContain("https://music.example.org");
    await fireEvent.click(screen.getByText("Wijzigen"));
    await waitFor(() =>
      expect(screen.getByLabelText("Serveradres").value).toBe("https://music.example.org"),
    );
    await fireEvent.input(screen.getByLabelText("Serveradres"), { target: { value: answerUrl } });
    await fireEvent.click(screen.getByText("Verbinden"));
  }

  it("stores another spelling of the same server without asking or signing out", async () => {
    await openChange("https://music.example.org");

    await waitFor(() =>
      expect(platform.system.setServerAddress).toHaveBeenCalledWith({
        url: "https://music.example.org",
        signOut: false,
      }),
    );
    expect(screen.queryByTestId("server-switch-confirm")).toBeNull();
    await waitFor(() => expect(screen.queryByTestId("first-run-server")).toBeNull());
  });

  it("asks before it moves to another server, and switches on yes", async () => {
    await openChange("https://music.example.net");

    await waitFor(() => expect(screen.getByTestId("server-switch-confirm")).toBeInTheDocument());
    expect(screen.getByText("Andere server gebruiken?")).toBeInTheDocument();
    expect(platform.system.setServerAddress).not.toHaveBeenCalled();

    await fireEvent.click(screen.getByTestId("server-switch-confirm-button"));

    await waitFor(() => expect(switchServer).toHaveBeenCalledWith("https://music.example.net"));
  });

  it("does nothing when the listener cancels the switch", async () => {
    await openChange("https://music.example.net");

    await waitFor(() => expect(screen.getByTestId("server-switch-confirm")).toBeInTheDocument());
    await fireEvent.click(screen.getByText("Annuleren"));

    expect(switchServer).not.toHaveBeenCalled();
    expect(platform.system.setServerAddress).not.toHaveBeenCalled();
    expect(screen.getByTestId("device-server").textContent).toContain("https://music.example.org");
  });

  it("shows a switch that failed and stays", async () => {
    vi.mocked(switchServer).mockRejectedValueOnce(new Error("bridge gone"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    await openChange("https://music.example.net");

    await waitFor(() => expect(screen.getByTestId("server-switch-confirm")).toBeInTheDocument());
    await fireEvent.click(screen.getByTestId("server-switch-confirm-button"));

    await waitFor(() =>
      expect(
        screen.getByText("Het adres kon niet worden opgeslagen: bridge gone"),
      ).toBeInTheDocument(),
    );
  });
});
