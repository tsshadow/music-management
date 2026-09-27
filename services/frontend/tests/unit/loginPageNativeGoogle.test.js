import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import LoginPage from "../../src/lib/LoginPage.svelte";
import { platform } from "../../src/lib/platform/index.js";
import { setLocaleFromAccount } from "../../src/lib/i18n/index.js";
import {
  credentials,
  mumaApiKey,
  mumaApiUrl,
  mumaSessionActive,
  mumaUser,
  signedOut,
  userPermissions,
} from "../../src/lib/store.js";

/**
 * "Sign in with Google" inside the Android shell (bug report 106). Google refuses its web sign-in
 * in a WebView, so the shell obtains the ID token natively and the page posts it to
 * `/api/auth/google` like the browser's button does. As in `loginPageNativeCredentials.test.js`,
 * `isNative` is flipped on the browser platform singleton to stand in for the shell.
 */

const MUMA_USER = { id: 1, username: "user", display_name: "Teun", permissions: ["music.play"] };

function server(
  google = { status: "ok", api_key: "key-1", refresh_token: "r-1", user: MUMA_USER },
) {
  return vi.fn(async (url) => {
    if (url.includes("/api/auth/google")) return { ok: true, json: async () => google };
    if (url.includes("/api/auth/setup-status"))
      return { ok: true, json: async () => ({ setup_required: false }) };
    return { ok: false, json: async () => ({}) };
  });
}

describe("LoginPage native Google sign-in", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "" });
    mumaApiUrl.set("https://lms.example/muma");
    mumaApiKey.set("");
    mumaSessionActive.set(false);
    mumaUser.set(null);
    userPermissions.set([]);
    signedOut.set(true);
    setLocaleFromAccount("nl");
    platform.system.isNative = true;
    global.fetch = server();
    document.head.querySelectorAll("script").forEach((s) => s.remove());
  });

  afterEach(() => {
    platform.system.isNative = false;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("offers the button when the APK can do it, and never loads Google's web script", async () => {
    vi.stubEnv("VITE_GOOGLE_CLIENT_ID", "client-id-1");
    vi.spyOn(platform.system, "googleSignInAvailable").mockResolvedValue(true);

    const { findByText } = render(LoginPage);

    expect(await findByText("Inloggen met Google")).toBeTruthy();
    const gsi = [...document.head.querySelectorAll("script")].find((s) =>
      s.src.includes("accounts.google.com"),
    );
    expect(gsi).toBeUndefined();
  });

  it("hides the button when the APK was built without a client ID", async () => {
    const available = vi.spyOn(platform.system, "googleSignInAvailable").mockResolvedValue(false);

    const { queryByText } = render(LoginPage);

    await waitFor(() => expect(available).toHaveBeenCalled());
    expect(queryByText("Inloggen met Google")).toBeNull();
  });

  it("signs in with the token and hands the session to the phone", async () => {
    vi.spyOn(platform.system, "googleSignInAvailable").mockResolvedValue(true);
    vi.spyOn(platform.system, "googleSignIn").mockResolvedValue("an-id-token");
    const saveCredentials = vi.spyOn(platform.system, "saveCredentials").mockResolvedValue();

    const { findByText } = render(LoginPage);
    await fireEvent.click(await findByText("Inloggen met Google"));

    await waitFor(() => expect(get(mumaSessionActive)).toBe(true));
    const [, request] = global.fetch.mock.calls.find(([url]) => url.includes("/api/auth/google"));
    expect(JSON.parse(request.body)).toEqual({ id_token: "an-id-token" });
    expect(get(credentials)).toMatchObject({ username: "user" });
    expect(get(credentials)).not.toHaveProperty("password");
    expect(saveCredentials).toHaveBeenCalledWith({
      url: "https://lms.example",
      username: "user",
      mumaApiKey: "key-1",
      mumaUserId: 1,
    });
    expect(get(signedOut)).toBe(false);
  });

  it("a closed account chooser shows nothing and calls nothing", async () => {
    vi.spyOn(platform.system, "googleSignInAvailable").mockResolvedValue(true);
    vi.spyOn(platform.system, "googleSignIn").mockResolvedValue(null);

    const { findByText, container } = render(LoginPage);
    await fireEvent.click(await findByText("Inloggen met Google"));

    await Promise.resolve();
    expect(global.fetch.mock.calls.some(([url]) => url.includes("/api/auth/google"))).toBe(false);
    expect(container.textContent).not.toContain("mislukt");
  });

  it("explains a refusal from Google in words", async () => {
    vi.spyOn(platform.system, "googleSignInAvailable").mockResolvedValue(true);
    vi.spyOn(platform.system, "googleSignIn").mockRejectedValue(
      Object.assign(new Error("no-credential"), { code: "no-credential" }),
    );

    const { findByText } = render(LoginPage);
    await fireEvent.click(await findByText("Inloggen met Google"));

    expect(await findByText(/Google gaf geen account terug/)).toBeTruthy();
  });

  it("shows the shell's reason for any other failure", async () => {
    vi.spyOn(platform.system, "googleSignInAvailable").mockResolvedValue(true);
    vi.spyOn(platform.system, "googleSignIn").mockRejectedValue(
      Object.assign(new Error("GetCredentialUnknownException"), { code: "failed" }),
    );

    const { findByText } = render(LoginPage);
    await fireEvent.click(await findByText("Inloggen met Google"));

    expect(await findByText(/GetCredentialUnknownException/)).toBeTruthy();
  });
});
