import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import LoginPage from "../../src/lib/LoginPage.svelte";
import { setLocaleFromAccount } from "../../src/lib/i18n/index.js";
import {
  credentials,
  mumaApiKey,
  mumaRefreshToken,
  mumaSessionActive,
  mumaUser,
  userPermissions,
} from "../../src/lib/store.js";
import { tokenRetry } from "../../src/lib/login.js";

tokenRetry.delayMs = 0;

const MUMA_USER = {
  id: 1,
  username: "demo-user",
  display_name: "Demo-User",
  permissions: ["music.play"],
};

/**
 * A fetch that answers each endpoint the login screen talks to.
 * Every part can be overridden per test.
 */
function api({
  ping = { "subsonic-response": { status: "ok" } },
  login = { ok: true, body: { api_key: "key-1", refresh_token: "refresh-1", user: MUMA_USER } },
  token = {
    ok: true,
    status: 200,
    body: { status: "ok", username: "demo-user", token: "the-subsonic-token" },
  },
  setupStatus = { setup_required: false },
  setup = { ok: true, body: {} },
  google = { status: "ok", api_key: "key-1", refresh_token: "refresh-1", user: MUMA_USER },
  accessRequest = {
    status: "ok",
    request: { id: 7, status: "pending", requested_at: "2026-01-01T01:00:00Z" },
  },
} = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/rest/ping")) return { ok: true, json: async () => ping };
    if (url.includes("/api/auth/login"))
      return { ok: login.ok, status: login.status, json: async () => login.body };
    if (url.includes("/api/auth/subsonic-token"))
      return { ok: token.ok, status: token.status, json: async () => token.body };
    if (url.includes("/api/auth/setup-status")) return { ok: true, json: async () => setupStatus };
    if (url.includes("/api/auth/setup")) return { ok: setup.ok, json: async () => setup.body };
    if (url.includes("/api/auth/google")) return { ok: true, json: async () => google };
    if (url.includes("/api/auth/access-request"))
      return { ok: true, json: async () => accessRequest };
    return { ok: true, json: async () => ({}) };
  });
}

async function fillIn(user, pass) {
  await fireEvent.input(screen.getByLabelText("Gebruikersnaam"), { target: { value: user } });
  await fireEvent.input(screen.getByLabelText("Wachtwoord"), { target: { value: pass } });
}

describe("LoginPage", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "" });
    mumaApiKey.set(null);
    mumaRefreshToken.set(null);
    mumaSessionActive.set(false);
    mumaUser.set(null);
    userPermissions.set([]);
    // Clearing mumaUser is a logout, and store.js drops the interface language
    // back to the browser's on logout -- which is English here. Pin it again, or
    // every assertion on Dutch interface text would fail.
    setLocaleFromAccount("nl");
    globalThis.fetch = api();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("asks for a username and password", () => {
    render(LoginPage);

    expect(screen.getByLabelText("Gebruikersnaam")).toBeTruthy();
    expect(screen.getByLabelText("Wachtwoord")).toBeTruthy();
    expect(screen.getByText("Verbinden")).toBeTruthy();
  });

  // Issue #101: the name is kept, the password is not -- not in the store, not in the form.
  it("a correct login stores the name and forgets the password", async () => {
    render(LoginPage);
    await fillIn("demo-user", "pw");

    await fireEvent.click(screen.getByText("Verbinden"));

    await waitFor(() => expect(get(credentials).username).toBe("demo-user"));
    expect(get(credentials)).not.toHaveProperty("password");
    await waitFor(() => expect(screen.getByLabelText("Wachtwoord").value).toBe(""));
  });

  it("a correct login also opens a management session", async () => {
    render(LoginPage);
    await fillIn("demo-user", "pw");

    await fireEvent.click(screen.getByText("Verbinden"));

    await waitFor(() => expect(get(mumaSessionActive)).toBe(true));
    expect(get(mumaApiKey)).toBe("key-1");
    expect(get(mumaRefreshToken)).toBe("refresh-1");
    expect(get(userPermissions)).toEqual(["music.play"]);
    expect(get(mumaUser)).toEqual(MUMA_USER);
  });

  // Issue #72: the management session is what fetches the Subsonic token, and there is no
  // password signature to fall back on -- a refused MuMa login is a refused sign-in.
  it("a refused management login is a refused sign-in", async () => {
    globalThis.fetch = api({ login: { ok: false, status: 401, body: {} } });
    render(LoginPage);
    await fillIn("demo-user", "pw");

    await fireEvent.click(screen.getByText("Verbinden"));

    await waitFor(() =>
      expect(screen.getByText("Fout: Ongeldige gebruikersnaam of wachtwoord")).toBeTruthy(),
    );
    expect(get(credentials).username).toBe("");
    expect(get(mumaSessionActive)).toBe(false);
    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("/rest/"))).toBe(false);
  });

  it("a server that cannot hand out a token reports no connection, not a wrong password", async () => {
    globalThis.fetch = api({ token: { ok: false, status: 503, body: {} } });
    render(LoginPage);
    await fillIn("demo-user", "pw");

    await fireEvent.click(screen.getByText("Verbinden"));

    await waitFor(() => expect(screen.getByText(/Fout|verbinding|server/i)).toBeTruthy());
    expect(get(credentials).username).toBe("");
  });

  it("reports the reason the server refused the login", async () => {
    globalThis.fetch = api({
      ping: { "subsonic-response": { status: "failed", error: { message: "Wrong password" } } },
    });
    render(LoginPage);
    await fillIn("demo-user", "wrong");

    await fireEvent.click(screen.getByText("Verbinden"));

    await waitFor(() => expect(screen.getByText("Fout: Wrong password")).toBeTruthy());
    expect(get(credentials).username).toBe("");
  });

  it("falls back to a generic message when the server gives no reason", async () => {
    globalThis.fetch = api({ ping: { "subsonic-response": { status: "failed" } } });
    render(LoginPage);
    await fillIn("demo-user", "wrong");

    await fireEvent.click(screen.getByText("Verbinden"));

    await waitFor(() =>
      expect(screen.getByText("Fout: Ongeldige gebruikersnaam of wachtwoord")).toBeTruthy(),
    );
  });

  it("reports a server it cannot reach at all", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    render(LoginPage);
    await fillIn("demo-user", "pw");

    await fireEvent.click(screen.getByText("Verbinden"));

    await waitFor(() =>
      expect(screen.getByText("Kon geen verbinding maken met de server")).toBeTruthy(),
    );
  });

  it("pressing enter in the password field logs in", async () => {
    render(LoginPage);
    await fillIn("demo-user", "pw");

    await fireEvent.keyDown(screen.getByLabelText("Wachtwoord"), { key: "Enter" });

    await waitFor(() => expect(get(credentials).username).toBe("demo-user"));
  });

  it("a remembered account's name is filled in on arrival, the password never", async () => {
    credentials.set({ url: "", username: "demo-user" });

    render(LoginPage);

    await waitFor(() => expect(screen.getByLabelText("Gebruikersnaam").value).toBe("demo-user"));
    expect(screen.getByLabelText("Wachtwoord").value).toBe("");
  });

  it("a server without any user asks to set one up", async () => {
    globalThis.fetch = api({ setupStatus: { setup_required: true } });

    render(LoginPage);

    await waitFor(() => expect(screen.getByText("Systeem Setup")).toBeTruthy());
    expect(screen.getByText("Account Aanmaken")).toBeTruthy();
  });

  it("the setup creates the first administrator", async () => {
    globalThis.fetch = api({ setupStatus: { setup_required: true } });
    render(LoginPage);
    await waitFor(() => expect(screen.getByText("Account Aanmaken")).toBeTruthy());
    await fillIn("demo-user", "pw");

    await fireEvent.click(screen.getByText("Account Aanmaken"));

    await waitFor(() => {
      const [, options] = globalThis.fetch.mock.calls.find(
        ([url]) => url.includes("/api/auth/setup") && !url.includes("status"),
      );
      expect(JSON.parse(options.body)).toEqual({
        username: "demo-user",
        password: "pw",
        display_name: "demo-user",
        role_name: "admin",
      });
    });
  });

  it("reports the reason a setup was refused", async () => {
    globalThis.fetch = api({
      setupStatus: { setup_required: true },
      setup: { ok: false, body: { detail: "Wachtwoord te kort" } },
    });
    render(LoginPage);
    await waitFor(() => expect(screen.getByText("Account Aanmaken")).toBeTruthy());
    await fillIn("demo-user", "x");

    await fireEvent.click(screen.getByText("Account Aanmaken"));

    await waitFor(() => expect(screen.getByText("Wachtwoord te kort")).toBeTruthy());
  });

  it("survives a setup-status check that fails", async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/setup-status")) throw new Error("network down");
      return { ok: true, json: async () => ({}) };
    });

    render(LoginPage);

    await waitFor(() => expect(screen.getByText("Inloggen")).toBeTruthy());
  });
});
