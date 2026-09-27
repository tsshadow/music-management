import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
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

const MUMA_USER = { id: 1, username: "user", display_name: "Teun", permissions: ["music.play"] };
const GOOGLE_IDENTITY = {
  subject: "google-sub-1",
  email: "user@example.com",
  display_name: "Teun",
  avatar_url: "https://example.com/user.jpg",
};
const REQUEST = { id: 7, status: "pending", requested_at: "2026-01-01T01:00:00Z" };

function api({ google = {}, accessRequest = { status: "ok", request: REQUEST } } = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/api/auth/google")) return { ok: true, json: async () => google };
    if (url.includes("/api/auth/access-request"))
      return { ok: true, json: async () => accessRequest };
    if (url.includes("/api/auth/setup-status"))
      return { ok: true, json: async () => ({ setup_required: false }) };
    return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
  });
}

/**
 * Renders the login screen with Google sign-in configured, runs the Google
 * Identity script the way the browser would, and returns the callback the page
 * registered so a test can deliver a credential to it.
 */
async function renderWithGoogle() {
  let registeredCallback;
  window.google = {
    accounts: {
      id: {
        initialize: ({ callback }) => {
          registeredCallback = callback;
        },
        renderButton: () => {},
      },
    },
  };

  render(LoginPage);

  await waitFor(() => {
    const script = [...document.head.querySelectorAll("script")].find((s) =>
      s.src.includes("accounts.google.com"),
    );
    expect(script).toBeTruthy();
    script.onload();
  });

  return (credential) => registeredCallback({ credential });
}

describe("LoginPage with Google sign-in", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "client-id-1");
    credentials.set({ url: "", username: "" });
    mumaApiKey.set(null);
    mumaRefreshToken.set(null);
    mumaSessionActive.set(false);
    mumaUser.set(null);
    userPermissions.set([]);
    setLocaleFromAccount("nl");
    globalThis.fetch = api();
    document.head.querySelectorAll("script").forEach((s) => s.remove());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete window.google;
    vi.restoreAllMocks();
  });

  it("a known Google account is signed straight in", async () => {
    globalThis.fetch = api({
      google: { status: "ok", api_key: "key-1", refresh_token: "refresh-1", user: MUMA_USER },
    });
    const signIn = await renderWithGoogle();

    await signIn("an-id-token");

    await waitFor(() => expect(get(mumaSessionActive)).toBe(true));
    expect(get(mumaApiKey)).toBe("key-1");
    expect(get(userPermissions)).toEqual(["music.play"]);
  });

  // Issue #101: the key used to be stored as a Subsonic password here. It signs nothing and
  // nothing re-logs in with it: the name is kept, the key stays the MuMa key only.
  it("keeps the account's name after a Google sign-in, and no password", async () => {
    globalThis.fetch = api({
      google: { status: "ok", api_key: "key-1", refresh_token: "refresh-1", user: MUMA_USER },
    });
    const signIn = await renderWithGoogle();

    await signIn("an-id-token");

    await waitFor(() => expect(get(credentials).username).toBe("user"));
    expect(get(credentials)).not.toHaveProperty("password");
    expect(localStorage.getItem("lms_credentials")).not.toContain("key-1");
  });

  it("an unknown Google account is offered the access request", async () => {
    globalThis.fetch = api({ google: { status: "unknown", google: GOOGLE_IDENTITY } });
    const signIn = await renderWithGoogle();

    await signIn("an-id-token");

    await waitFor(() => expect(screen.getByText(/Hallo Teun/)).toBeTruthy());
    expect(screen.getByText("Toegang aanvragen")).toBeTruthy();
  });

  it("submitting the request reports it as pending", async () => {
    globalThis.fetch = api({ google: { status: "unknown", google: GOOGLE_IDENTITY } });
    const signIn = await renderWithGoogle();
    await signIn("an-id-token");
    await waitFor(() => expect(screen.getByText("Toegang aanvragen")).toBeTruthy());

    await fireEvent.click(screen.getByText("Toegang aanvragen"));

    await waitFor(() => expect(screen.getByText(/in behandeling/)).toBeTruthy());
    const [, options] = globalThis.fetch.mock.calls.find(([url]) =>
      url.includes("/api/auth/access-request"),
    );
    expect(JSON.parse(options.body)).toEqual({ id_token: "an-id-token" });
  });

  it("a refused request does not move on to pending", async () => {
    // The reason is stored, but this branch has no place to show it: the error
    // line only exists on the ordinary login form.
    globalThis.fetch = api({
      google: { status: "unknown", google: GOOGLE_IDENTITY },
      accessRequest: { status: "error", detail: "Al aangevraagd" },
    });
    const signIn = await renderWithGoogle();
    await signIn("an-id-token");
    await waitFor(() => expect(screen.getByText("Toegang aanvragen")).toBeTruthy());

    await fireEvent.click(screen.getByText("Toegang aanvragen"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([url]) => url.includes("/api/auth/access-request")),
      ).toBe(true),
    );
    expect(screen.queryByText(/in behandeling/)).toBeNull();
  });

  it("an account whose request is still pending is told so", async () => {
    globalThis.fetch = api({ google: { status: "request_pending", request: REQUEST } });
    const signIn = await renderWithGoogle();

    await signIn("an-id-token");

    await waitFor(() => expect(screen.getByText(/in behandeling/)).toBeTruthy());
  });

  it("an approved request invites the account to log in", async () => {
    globalThis.fetch = api({
      google: { status: "request_approved", request: { ...REQUEST, status: "approved" } },
    });
    const signIn = await renderWithGoogle();

    await signIn("an-id-token");

    await waitFor(() => expect(screen.getByText(/goedgekeurd/)).toBeTruthy());
  });

  it("a rejected request says so", async () => {
    globalThis.fetch = api({
      google: { status: "request_rejected", request: { ...REQUEST, status: "rejected" } },
    });
    const signIn = await renderWithGoogle();

    await signIn("an-id-token");

    await waitFor(() => expect(screen.getByText(/afgewezen/)).toBeTruthy());
  });

  it("going back returns to the ordinary login form", async () => {
    globalThis.fetch = api({ google: { status: "unknown", google: GOOGLE_IDENTITY } });
    const signIn = await renderWithGoogle();
    await signIn("an-id-token");
    await waitFor(() => expect(screen.getByText("Toegang aanvragen")).toBeTruthy());

    await fireEvent.click(screen.getByText("Terug naar inloggen"));

    expect(screen.getByLabelText("Gebruikersnaam")).toBeTruthy();
  });

  it("reports a Google check that never arrives", async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/google")) throw new Error("network down");
      return { ok: true, json: async () => ({ setup_required: false }) };
    });
    const signIn = await renderWithGoogle();

    await signIn("an-id-token");

    await waitFor(() =>
      expect(screen.getByText("Kon geen verbinding maken met de Google login API")).toBeTruthy(),
    );
  });
});
