import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import ProfileButton from "../../src/lib/ProfileButton.svelte";
import { platform } from "../../src/lib/platform/index.js";
import {
  credentials,
  currentTrack,
  equalizerSettings,
  EQUALIZER_DEFAULT,
  homeShortcutCount,
  mumaApiUrl,
  playerState,
  playlist,
  setupStepsSeen,
  syncMode,
  trackPageSize,
  DEFAULT_TRACK_PAGE_SIZE,
  mumaApiKey,
  mumaRefreshToken,
  mumaSessionActive,
  userPermissions,
  mumaUser,
  signedOut,
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

/**
 * The whole logout gesture since issue #80: open the menu, pick "Uitloggen", then confirm it in
 * the dialog that now always comes first.
 */
async function logOut(container, getByText, getByTestId) {
  await openMenu(container);
  await fireEvent.click(getByText("Uitloggen"));
  await fireEvent.click(getByTestId("logout-confirm-button"));
}

describe("ProfileButton logout", () => {
  let reload;

  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "demo-user" });
    mumaApiKey.set("key-1");
    mumaRefreshToken.set("refresh-1");
    mumaSessionActive.set(true);
    userPermissions.set(["admin"]);
    mumaUser.set({ username: "demo-user" });
    signedOut.set(false);
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

    const { container, getByText, getByTestId } = render(ProfileButton, { onNavigate: vi.fn() });
    await logOut(container, getByText, getByTestId);

    // The native call went out, but nothing else has happened yet -- the whole point of
    // awaiting it first.
    expect(signOut).toHaveBeenCalledOnce();
    expect(reload).not.toHaveBeenCalled();
    expect(get(credentials).username).toBe("demo-user");

    resolveSignOut();
    await waitFor(() => expect(reload).toHaveBeenCalledOnce());

    expect(get(credentials).username).toBe("");
    expect(get(credentials)).not.toHaveProperty("password");
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

    const { container, getByText, getByTestId } = render(ProfileButton, { onNavigate: vi.fn() });
    await logOut(container, getByText, getByTestId);

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(get(credentials).username).toBe("");
  });

  // Bug report 106: the native call crashed on a background thread and never answered, so the
  // logout awaited it forever and the button visibly did nothing.
  it("a phone sign-out that never answers does not hold the logout up", async () => {
    vi.useFakeTimers();
    try {
      vi.spyOn(platform.system, "signOut").mockReturnValue(new Promise(() => {}));
      vi.spyOn(console, "warn").mockImplementation(() => {});

      const { container, getByText, getByTestId } = render(ProfileButton, { onNavigate: vi.fn() });
      await logOut(container, getByText, getByTestId);
      await vi.advanceTimersByTimeAsync(10_000);

      expect(reload).toHaveBeenCalledOnce();
      expect(get(credentials)).not.toHaveProperty("password");
      expect(get(signedOut)).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("marks the device as signed out, and keeps the mark across the session reset", async () => {
    const { container, getByText, getByTestId } = render(ProfileButton, { onNavigate: vi.fn() });
    await logOut(container, getByText, getByTestId);
    await waitFor(() => expect(reload).toHaveBeenCalledOnce());

    expect(get(signedOut)).toBe(true);
    expect(window.localStorage.getItem("muma_signed_out")).toBe("true");
  });

  it("a browser tab's no-op sign-out does not block the reload", async () => {
    const { container, getByText, getByTestId } = render(ProfileButton, { onNavigate: vi.fn() });
    await logOut(container, getByText, getByTestId);

    await waitFor(() => expect(reload).toHaveBeenCalledOnce());
    expect(get(credentials).username).toBe("");
  });

  // The second half of the bug: everything else the previous person left in localStorage --
  // queue, current track, player, equalizer, page size, account settings -- used to survive, so
  // the next person to sign in on this browser started inside their session.
  it("leaves nothing of the previous user's session behind", async () => {
    playlist.set([{ id: "t1" }, { id: "t2" }]);
    currentTrack.set({ id: "t1", title: "Raise Your Fist" });
    playerState.set({
      playing: true,
      volume: 20,
      progress: 42,
      duration: 240,
      shuffle: true,
      repeat: "all",
    });
    syncMode.set("host");
    trackPageSize.set(200);
    equalizerSettings.set({ ...EQUALIZER_DEFAULT, enabled: true, preamp: 3 });
    homeShortcutCount.set(3);
    setupStepsSeen.set(["language"]);
    mumaApiUrl.set("https://muma.example");

    const { container, getByText, getByTestId } = render(ProfileButton, { onNavigate: vi.fn() });
    await logOut(container, getByText, getByTestId);
    await waitFor(() => expect(reload).toHaveBeenCalledOnce());

    expect(get(playlist)).toEqual([]);
    expect(get(currentTrack)).toBeNull();
    expect(get(playerState)).toMatchObject({
      playing: false,
      progress: 0,
      shuffle: false,
      repeat: "none",
    });
    expect(get(syncMode)).toBe("off");
    expect(get(trackPageSize)).toBe(DEFAULT_TRACK_PAGE_SIZE);
    expect(get(equalizerSettings).enabled).toBe(false);
    expect(get(homeShortcutCount)).toBe(8);
    expect(get(setupStepsSeen)).toEqual([]);
    for (const key of [
      "lms_playlist",
      "lms_current_track",
      "lms_equalizer",
      "lms_homeShortcutCount",
    ]) {
      expect(window.localStorage.getItem(key)).toBeNull();
    }
    // Which server this browser talks to is the device's, not the account's.
    expect(get(mumaApiUrl)).toBe("https://muma.example");
  });
  // Issue #80 / style guide "Session controls": a logout always confirms first, saying what is
  // lost and what is kept.
  describe("confirmation", () => {
    /**
     * The shared `setup.js` stub for `element.animate()` never calls `onfinish`, so a modal's
     * outro never ends and a closed dialog stays in the DOM. Closing is the point of the cancel
     * test, so this one finishes every animation as soon as Svelte listens for it.
     */
    function finishAnimations() {
      vi.spyOn(Element.prototype, "animate").mockImplementation(() => {
        const animation = { cancel() {}, currentTime: 0, playState: "finished" };
        Object.defineProperty(animation, "onfinish", {
          set(callback) {
            queueMicrotask(() => callback?.());
          },
        });
        return animation;
      });
    }

    it("asks first, and does nothing until the answer", async () => {
      const signOut = vi.spyOn(platform.system, "signOut").mockResolvedValue();

      const { container, getByText, getByTestId, getByRole } = render(ProfileButton, {
        onNavigate: vi.fn(),
      });
      await openMenu(container);
      await fireEvent.click(getByText("Uitloggen"));

      const dialog = getByRole("dialog");
      expect(dialog.getAttribute("aria-label")).toBe("Uitloggen?");
      expect(getByTestId("logout-confirm").textContent).toContain(
        "Het afspelen stopt en je wachtrij wordt leeggemaakt.",
      );
      // Rendered outside the top bar, whose backdrop blur would otherwise clip the overlay.
      expect(container.contains(dialog)).toBe(false);
      expect(signOut).not.toHaveBeenCalled();
      expect(reload).not.toHaveBeenCalled();
      expect(get(credentials).username).toBe("demo-user");
    });

    it("cancel keeps everything as it was", async () => {
      finishAnimations();
      const signOut = vi.spyOn(platform.system, "signOut").mockResolvedValue();
      playlist.set([{ id: "t1" }]);

      const { container, getByText, queryByRole } = render(ProfileButton, {
        onNavigate: vi.fn(),
      });
      await openMenu(container);
      await fireEvent.click(getByText("Uitloggen"));
      await fireEvent.click(getByText("Annuleren"));

      await waitFor(() => expect(queryByRole("dialog")).toBeNull());
      expect(signOut).not.toHaveBeenCalled();
      expect(reload).not.toHaveBeenCalled();
      expect(get(credentials).username).toBe("demo-user");
      expect(get(mumaApiKey)).toBe("key-1");
      expect(get(playlist)).toEqual([{ id: "t1" }]);
      expect(get(signedOut)).toBe(false);
    });

    it("confirm runs the sign-out exactly once, even when tapped twice", async () => {
      const signOut = vi.spyOn(platform.system, "signOut").mockResolvedValue();

      const { container, getByText, getByTestId } = render(ProfileButton, {
        onNavigate: vi.fn(),
      });
      await openMenu(container);
      await fireEvent.click(getByText("Uitloggen"));
      const confirm = getByTestId("logout-confirm-button");
      await fireEvent.click(confirm);
      await fireEvent.click(confirm);

      await waitFor(() => expect(reload).toHaveBeenCalledOnce());
      expect(signOut).toHaveBeenCalledOnce();
      expect(get(credentials).username).toBe("");
    });

    it("only the phone promises to keep downloads", async () => {
      const native = Object.getOwnPropertyDescriptor(platform.system, "isNative");
      const kept = "Je downloads blijven op dit apparaat staan.";
      try {
        const first = render(ProfileButton, { onNavigate: vi.fn() });
        await openMenu(first.container);
        await fireEvent.click(first.getByText("Uitloggen"));
        expect(first.getByTestId("logout-confirm").textContent).not.toContain(kept);
        first.unmount();

        Object.defineProperty(platform.system, "isNative", { configurable: true, value: true });
        const second = render(ProfileButton, { onNavigate: vi.fn() });
        await openMenu(second.container);
        await fireEvent.click(second.getByText("Uitloggen"));
        expect(second.getByTestId("logout-confirm").textContent).toContain(kept);
      } finally {
        if (native) Object.defineProperty(platform.system, "isNative", native);
      }
    });
  });
});
