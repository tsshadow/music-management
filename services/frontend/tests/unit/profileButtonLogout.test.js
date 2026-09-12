import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import ProfileButton from "../../src/lib/ProfileButton.svelte";
import { platform } from "../../src/lib/platform/index.js";
import {
  credentials,
  mumaApiKey,
  mumaRefreshToken,
  mumaSessionActive,
  userPermissions,
  mumaUser,
} from "../../src/lib/store.js";

/**
 * The bug this guards against: logging out inside the Capacitor shell used to do nothing
 * visible, because `handleLogout` reloaded the page before -- in fact without ever -- telling
 * Kotlin to drop its own stored credentials, and `bootstrapShell()` read them straight back out
 * on the next boot. The fix is ordering: await `platform.system.signOut()` before anything else,
 * so a native shell's own state is gone before the reload that would otherwise resurrect it. A
 * plain browser tab has no such state; `signOut()` there is a no-op that resolves at once, so the
 * same ordering costs it nothing.
 */

function openMenu(container) {
  const toggle = container.querySelector("button");
  return fireEvent.click(toggle);
}

describe("ProfileButton logout", () => {
  let reload;

  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "user", password: "hunter2" });
    mumaApiKey.set("key-1");
    mumaRefreshToken.set("refresh-1");
    mumaSessionActive.set(true);
    userPermissions.set(["admin"]);
    mumaUser.set({ username: "user" });
    window.localStorage.clear();
    window.localStorage.setItem("lms_active_view", "albums");

    // jsdom's `Location.reload` is not a configurable own property, so `vi.spyOn` on it
    // throws; replacing the whole `window.location` property is what jsdom test suites do
    // instead.
    reload = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("waits for the phone's sign-out before clearing the session and reloading", async () => {
    let resolveSignOut;
    const signOut = vi.spyOn(platform.system, "signOut").mockReturnValue(
      new Promise((resolve) => {
        resolveSignOut = resolve;
      }),
    );

    const { container, getByText } = render(ProfileButton, { onNavigate: vi.fn() });
    await openMenu(container);
    await fireEvent.click(getByText("Uitloggen"));

    // The native call went out, but nothing else has happened yet -- the whole point of
    // awaiting it first.
    expect(signOut).toHaveBeenCalledOnce();
    expect(reload).not.toHaveBeenCalled();
    expect(get(credentials).username).toBe("user");

    resolveSignOut();
    await waitFor(() => expect(reload).toHaveBeenCalledOnce());

    expect(get(credentials).username).toBe("");
    expect(get(credentials).password).toBe("");
    expect(get(mumaApiKey)).toBe("");
    expect(get(mumaRefreshToken)).toBe("");
    expect(get(mumaSessionActive)).toBe(false);
    expect(get(userPermissions)).toEqual([]);
    expect(get(mumaUser)).toBeNull();
    expect(window.localStorage.getItem("lms_active_view")).toBeNull();
  });

  it("still logs out when the phone's sign-out fails", async () => {
    vi.spyOn(platform.system, "signOut").mockRejectedValue(new Error("no bridge"));
    vi.spyOn(console, "warn").mockImplementation(() => {});

    const { container, getByText } = render(ProfileButton, { onNavigate: vi.fn() });
    await openMenu(container);
    await fireEvent.click(getByText("Uitloggen"));

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(get(credentials).username).toBe("");
  });

  it("a browser tab's no-op sign-out does not block the reload", async () => {
    const { container, getByText } = render(ProfileButton, { onNavigate: vi.fn() });
    await openMenu(container);
    await fireEvent.click(getByText("Uitloggen"));

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(get(credentials).username).toBe("");
  });
});
