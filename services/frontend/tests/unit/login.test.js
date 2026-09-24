import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import { startManagementSession } from "../../src/lib/login.js";
import {
  isAdmin,
  mumaApiKey,
  mumaRefreshToken,
  mumaSessionActive,
  mumaUser,
  userPermissions,
} from "../../src/lib/store.js";

/**
 * `startManagementSession` reads MuMa's own login answer. LMS used to answer
 * `/muma/api/auth/login` itself -- flat, and with its own shared `api-key` for
 * every user -- so these pin what a session is built from now.
 */

const MUMA_ANSWER = {
  status: "ok",
  api_key: "own-key-of-user",
  access_token: "own-key-of-user",
  refresh_token: "refresh-1",
  user: {
    id: 3,
    username: "user",
    is_admin: false,
    role_name: "user",
    permissions: ["music.play"],
  },
};

/** A fetch whose login answers `body` with `ok`. */
function loginAnswering(body, ok = true) {
  return vi.fn(async () => ({ ok, json: async () => body }));
}

describe("login - startManagementSession", () => {
  beforeEach(() => {
    mumaApiKey.set("");
    mumaRefreshToken.set("");
    mumaSessionActive.set(false);
    mumaUser.set(null);
    userPermissions.set([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("stores the user's own key, refresh token, permissions and account", async () => {
    globalThis.fetch = loginAnswering(MUMA_ANSWER);

    expect(await startManagementSession("user", "pw")).toBe(true);

    expect(get(mumaApiKey)).toBe("own-key-of-user");
    expect(get(mumaRefreshToken)).toBe("refresh-1");
    expect(get(userPermissions)).toEqual(["music.play"]);
    expect(get(mumaUser)).toEqual(MUMA_ANSWER.user);
    expect(get(mumaSessionActive)).toBe(true);
  });

  it("posts the pair to the muma login", async () => {
    globalThis.fetch = loginAnswering(MUMA_ANSWER);

    await startManagementSession("user", "pw");

    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toMatch(/\/api\/auth\/login$/);
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({ username: "user", password: "pw" });
  });

  it("an account that is not an administrator does not become one", async () => {
    globalThis.fetch = loginAnswering(MUMA_ANSWER);

    await startManagementSession("user", "pw");

    expect(get(mumaUser).is_admin).toBe(false);
    expect(get(isAdmin)).not.toBe(true);
  });

  it("an administrator is recognised from the account MuMa returns", async () => {
    globalThis.fetch = loginAnswering({
      ...MUMA_ANSWER,
      user: { ...MUMA_ANSWER.user, is_admin: true, role_name: "admin" },
    });

    await startManagementSession("user", "pw");

    expect(get(isAdmin)).toBe(true);
  });

  it("the old flat LMS answer starts no session and stores nothing", async () => {
    // What LMS used to send: no `user`, and its own api-key for everybody.
    globalThis.fetch = loginAnswering({
      id: 3,
      username: "user",
      display_name: "user",
      is_admin: true,
      api_key: "lms-shared-key",
    });

    expect(await startManagementSession("user", "pw")).toBe(false);

    expect(get(mumaApiKey)).toBe("");
    expect(get(mumaUser)).toBe(null);
    expect(get(mumaSessionActive)).toBe(false);
  });

  it("an answer without a key starts no session", async () => {
    globalThis.fetch = loginAnswering({ ...MUMA_ANSWER, api_key: "" });

    expect(await startManagementSession("user", "pw")).toBe(false);
    expect(get(mumaApiKey)).toBe("");
  });

  it("a missing permissions list becomes an empty one", async () => {
    const user = { ...MUMA_ANSWER.user };
    delete user.permissions;
    globalThis.fetch = loginAnswering({ ...MUMA_ANSWER, user });

    expect(await startManagementSession("user", "pw")).toBe(true);
    expect(get(userPermissions)).toEqual([]);
  });

  it("a refused login starts no session", async () => {
    globalThis.fetch = loginAnswering({ detail: "Invalid username or password" }, false);

    expect(await startManagementSession("user", "wrong")).toBe(false);
    expect(get(mumaApiKey)).toBe("");
  });

  it("an unreachable server starts no session", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    expect(await startManagementSession("user", "pw")).toBe(false);
    expect(get(mumaSessionActive)).toBe(false);
  });
});
