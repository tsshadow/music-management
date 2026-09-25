import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import { canonicalUsername, signIn, startManagementSession } from "../../src/lib/login.js";
import {
  credentials,
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

/**
 * Account names are case-insensitive, and the account's own spelling is the one
 * that is stored and signed in with afterwards -- never the typed one. "Teun"
 * typed for "user" used to travel on as Subsonic `u=`, and LMS created a second
 * user for it (docs/bug-reports/074-login-case-forks-user-identity.md).
 */
describe("login - the account's own spelling", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "", password: "" });
    mumaApiKey.set("");
    mumaSessionActive.set(false);
    mumaUser.set(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** Subsonic ping says ok; MuMa's login answers with `account`. */
  function serverAnswering(account) {
    return vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) {
        return { ok: true, json: async () => ({ ...MUMA_ANSWER, user: account }) };
      }
      return { json: async () => ({ "subsonic-response": { status: "ok" } }) };
    });
  }

  it("stores the name MuMa returned, not the case it was typed in", async () => {
    globalThis.fetch = serverAnswering({ ...MUMA_ANSWER.user, username: "user" });

    const result = await signIn("Teun", "pw");

    expect(result).toEqual({ ok: true, username: "user" });
    expect(get(credentials).username).toBe("user");
    expect(get(credentials).password).toBe("pw");
  });

  it("keeps the typed name when there is no management session to go by", async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) return { ok: false, json: async () => ({}) };
      return { json: async () => ({ "subsonic-response": { status: "ok" } }) };
    });

    const result = await signIn("Teun", "pw");

    expect(result).toEqual({ ok: true, username: "Teun" });
    expect(get(credentials).username).toBe("Teun");
  });

  it("adopts only a spelling of the same name", () => {
    expect(canonicalUsername("Teun", { username: "user" })).toBe("user");
    expect(canonicalUsername("TEUN", { username: "user" })).toBe("user");
    expect(canonicalUsername("user", { username: "someone-else" })).toBe("user");
    expect(canonicalUsername("user", null)).toBe("user");
    expect(canonicalUsername("user", { username: "" })).toBe("user");
  });
});
