import { describe, it, expect, vi, beforeEach } from "vitest";
import { get } from "svelte/store";
import { hostOf, sameServer, switchServer, useServerAddress } from "../../src/lib/serverAddress.js";
import {
  credentials,
  mumaApiUrl,
  mumaUser,
  signedOut,
  userPermissions,
} from "../../src/lib/store.js";

/** The steps around the first-run server screen (issue #192). */
function shell() {
  return {
    system: {
      isNative: true,
      setServerAddress: vi.fn(async () => {}),
      loadServerUrl: vi.fn(async () => ({
        subsonic: "https://music.example.net",
        mumaApi: "https://music.example.net/muma",
        configured: true,
      })),
    },
  };
}

describe("serverAddress", () => {
  beforeEach(() => {
    credentials.set({ url: "https://music.example.org", username: "demo-user" });
    mumaApiUrl.set("https://music.example.org/muma");
    signedOut.set(false);
  });

  it("names the host of an address", () => {
    expect(hostOf("https://music.example.org/lms")).toBe("music.example.org");
    expect(hostOf("https://music.example.org:8443")).toBe("music.example.org:8443");
    expect(hostOf("not a url")).toBe("not a url");
    expect(hostOf(undefined)).toBe("");
  });

  it("tells another spelling of a server from another server", () => {
    expect(sameServer("https://Music.Example.org/", "music.example.org")).toBe(true);
    expect(sameServer("https://music.example.org/lms", "https://music.example.org")).toBe(false);
    expect(sameServer("https://music.example.org", "https://music.example.net")).toBe(false);
    expect(sameServer("", "https://music.example.net")).toBe(false);
    expect(sameServer("https://exa mple", "https://exa mple")).toBe(true);
  });

  it("stores an address on the phone and points the stores at it", async () => {
    const platform = shell();

    await useServerAddress("https://music.example.net", { platform });

    expect(platform.system.setServerAddress).toHaveBeenCalledWith({
      url: "https://music.example.net",
      signOut: false,
    });
    expect(get(credentials).url).toBe("https://music.example.net");
    expect(get(mumaApiUrl)).toBe("https://music.example.net/muma");
  });

  it("switches server the way a logout ends a session", async () => {
    const platform = shell();
    mumaUser.set({ id: 1 });
    userPermissions.set(["admin"]);

    await switchServer("https://music.example.net", { platform });

    expect(platform.system.setServerAddress).toHaveBeenCalledWith({
      url: "https://music.example.net",
      signOut: true,
    });
    expect(get(mumaUser)).toBeNull();
    expect(get(userPermissions)).toEqual([]);
    expect(get(signedOut)).toBe(true);
  });
});
