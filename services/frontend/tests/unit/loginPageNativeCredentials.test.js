import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/svelte";
import LoginPage from "../../src/lib/LoginPage.svelte";
import { platform } from "../../src/lib/platform/index.js";
import { credentials, mumaApiUrl } from "../../src/lib/store.js";

/**
 * The other half of the sign-out fix: after a fresh sign-in on this screen inside the Capacitor
 * shell, Kotlin has to learn the pair too, or downloads and Android Auto stay
 * signed out with whatever (or nothing) it had before. There is no Capacitor bridge in this test
 * environment, so `platform` resolves to the browser implementation; `isNative` is flipped on
 * that shared singleton for the duration of each test to stand in for the shell, the same way
 * `serverUrl()` here reads back through the ordinary web stores rather than a plugin.
 */
function fakeServer({ ping = "ok" } = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/rest/ping")) {
      return { json: async () => ({ "subsonic-response": { status: ping } }) };
    }
    if (url.includes("/api/auth/login")) {
      return {
        ok: true,
        json: async () => ({ api_key: "own-key", user: { id: 1, username: "user" } }),
      };
    }
    if (url.includes("/api/auth/subsonic-token")) {
      return {
        ok: true,
        json: async () => ({ status: "ok", username: "user", token: "the-subsonic-token" }),
      };
    }
    if (url.includes("/api/auth/setup-status")) {
      return { ok: true, json: async () => ({ setup_required: false }) };
    }
    return { ok: false, json: async () => ({}) };
  });
}

describe("LoginPage native credential save", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "", password: "" });
    mumaApiUrl.set("https://lms.example/muma");
    platform.system.isNative = true;
    global.fetch = fakeServer();
  });

  afterEach(() => {
    platform.system.isNative = false;
    vi.restoreAllMocks();
  });

  it("saves a verified pair back to the phone", async () => {
    const saveCredentials = vi.spyOn(platform.system, "saveCredentials").mockResolvedValue();

    const { getByLabelText, getByText } = render(LoginPage);
    await fireEvent.input(getByLabelText("Gebruikersnaam"), { target: { value: "user" } });
    await fireEvent.input(getByLabelText("Wachtwoord"), { target: { value: "hunter2" } });
    await fireEvent.click(getByText("Verbinden"));

    await waitFor(() => expect(saveCredentials).toHaveBeenCalledOnce());
    expect(saveCredentials).toHaveBeenCalledWith({
      url: "https://lms.example",
      username: "user",
      password: "hunter2",
    });
  });

  // Bug report 074: the phone signs its own Subsonic calls with what is saved
  // here, and a case variant made LMS create a second user for the account.
  it("saves the account's own spelling, not the case it was typed in", async () => {
    global.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) {
        return {
          ok: true,
          json: async () => ({ api_key: "own-key", user: { id: 1, username: "user" } }),
        };
      }
      return fakeServer()(url);
    });
    const saveCredentials = vi.spyOn(platform.system, "saveCredentials").mockResolvedValue();

    const { getByLabelText, getByText } = render(LoginPage);
    await fireEvent.input(getByLabelText("Gebruikersnaam"), { target: { value: "Teun" } });
    await fireEvent.input(getByLabelText("Wachtwoord"), { target: { value: "hunter2" } });
    await fireEvent.click(getByText("Verbinden"));

    await waitFor(() => expect(saveCredentials).toHaveBeenCalledOnce());
    expect(saveCredentials).toHaveBeenCalledWith({
      url: "https://lms.example",
      username: "user",
      password: "hunter2",
    });
  });

  it("does not save a rejected sign-in", async () => {
    global.fetch = fakeServer({ ping: "failed" });
    const saveCredentials = vi.spyOn(platform.system, "saveCredentials").mockResolvedValue();

    const { getByLabelText, getByText } = render(LoginPage);
    await fireEvent.input(getByLabelText("Gebruikersnaam"), { target: { value: "user" } });
    await fireEvent.input(getByLabelText("Wachtwoord"), { target: { value: "wrong" } });
    await fireEvent.click(getByText("Verbinden"));

    await waitFor(() => expect(getByText(/Ongeldige gebruikersnaam/)).toBeTruthy());
    expect(saveCredentials).not.toHaveBeenCalled();
  });

  it("a failed bridge write does not surface as a login error", async () => {
    vi.spyOn(platform.system, "saveCredentials").mockRejectedValue(new Error("no bridge"));
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { getByLabelText, getByText, queryByText } = render(LoginPage);
    await fireEvent.input(getByLabelText("Gebruikersnaam"), { target: { value: "user" } });
    await fireEvent.input(getByLabelText("Wachtwoord"), { target: { value: "hunter2" } });
    await fireEvent.click(getByText("Verbinden"));

    await waitFor(() => expect(console.warn).toHaveBeenCalled());
    expect(queryByText(/Fout/)).toBeNull();
  });
});
