import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  TOKEN_ATTEMPTS,
  canonicalUsername,
  signIn,
  startManagementSession,
  tokenRetry,
} from "../../src/lib/login.js";

tokenRetry.delayMs = 0;
import {
  credentials,
  isAdmin,
  mumaApiKey,
  mumaRefreshToken,
  mumaSessionActive,
  mumaUser,
  subsonicToken,
  userPermissions,
} from "../../src/lib/store.js";
import { md5 } from "../../src/lib/md5.js";

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

  /** Subsonic ping says ok; MuMa's login answers with `account`, the token endpoint with LMS's name. */
  function serverAnswering(account, lmsName = account.username) {
    return vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) {
        return { ok: true, json: async () => ({ ...MUMA_ANSWER, user: account }) };
      }
      if (url.includes("/api/auth/subsonic-token")) {
        return {
          ok: true,
          json: async () => ({ status: "ok", username: lmsName, token: "the-subsonic-token" }),
        };
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

  it("takes LMS's spelling from the token when MuMa's answer had none to go by", async () => {
    globalThis.fetch = serverAnswering({ ...MUMA_ANSWER.user, username: "" }, "user");

    const result = await signIn("Teun", "pw");

    expect(result).toEqual({ ok: true, username: "user" });
    expect(get(credentials).username).toBe("user");
  });

  it("adopts only a spelling of the same name", () => {
    expect(canonicalUsername("Teun", { username: "user" })).toBe("user");
    expect(canonicalUsername("TEUN", { username: "user" })).toBe("user");
    expect(canonicalUsername("user", { username: "someone-else" })).toBe("user");
    expect(canonicalUsername("user", null)).toBe("user");
    expect(canonicalUsername("user", { username: "" })).toBe("user");
  });
});

/**
 * Bug report 103: a sign-in puts the password in a POST body only. The ping
 * that proves LMS accepts the account is signed with the Subsonic token the
 * management session fetches. Since issue #72 there is no password fallback:
 * without a session or a token there is no sign-in, and no URL ever carries it.
 */
describe("login - signing the ping with the Subsonic token", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "", password: "" });
    subsonicToken.set({ username: "", token: "" });
    mumaApiKey.set("");
    mumaSessionActive.set(false);
    mumaUser.set(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** A server whose login, token endpoint and ping answer as given. */
  function server({
    token = { username: "user", token: "the-subsonic-token" },
    pingAccepts = () => true,
  } = {}) {
    return vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) return { ok: true, json: async () => MUMA_ANSWER };
      if (url.includes("/api/auth/subsonic-token")) {
        if (!token) return { ok: false, status: 404, json: async () => ({}) };
        return { ok: true, json: async () => ({ status: "ok", ...token }) };
      }
      const status = pingAccepts(new URL(url)) ? "ok" : "failed";
      return {
        json: async () => ({
          "subsonic-response": {
            status,
            error: { code: 40, message: "Wrong username or password" },
          },
        }),
      };
    });
  }

  /** The URL of every /rest/ping the fake server saw. */
  function pings() {
    return globalThis.fetch.mock.calls
      .map(([url]) => url)
      .filter((url) => url.includes("/rest/ping"))
      .map((url) => new URL(url));
  }

  it("never puts the password in a URL when a token comes back", async () => {
    globalThis.fetch = server();

    const result = await signIn("user", "hunter2");

    expect(result).toEqual({ ok: true, username: "user" });
    for (const [url] of globalThis.fetch.mock.calls) expect(url).not.toContain("hunter2");
    const [ping] = pings();
    expect(ping.searchParams.has("p")).toBe(false);
    expect(ping.searchParams.get("t")).toBe(md5(`the-subsonic-token${ping.searchParams.get("s")}`));
    expect(get(subsonicToken)).toEqual({ username: "user", token: "the-subsonic-token" });
  });

  it("fails as unreachable, and sends no ping, when no token can be had", async () => {
    globalThis.fetch = server({ token: null });

    const result = await signIn("user", "hunter2");

    expect(result).toEqual({ ok: false, reason: "offline", message: "" });
    expect(pings()).toHaveLength(0);
    expect(get(credentials).username).toBe("");
    expect(get(mumaApiKey)).toBe("");
  });

  it("a token LMS refuses is dropped and the sign-in fails -- no second ping with the password", async () => {
    globalThis.fetch = server({ pingAccepts: () => false });

    const result = await signIn("user", "hunter2");

    expect(result.ok).toBe(false);
    expect(result.reason).toBe("rejected");
    expect(pings()).toHaveLength(1);
    expect(pings()[0].searchParams.has("p")).toBe(false);
    expect(get(subsonicToken).token).toBe("");
  });

  it("no request of the sign-in carries the password in its URL, whatever fails", async () => {
    for (const setup of [{ token: null }, { pingAccepts: () => false }, {}]) {
      credentials.set({ url: "https://lms.example", username: "", password: "" });
      subsonicToken.set({ username: "", token: "" });
      globalThis.fetch = server(setup);

      await signIn("user", "hunter2");

      for (const [url] of globalThis.fetch.mock.calls) expect(url).not.toContain("hunter2");
    }
  });

  it("a wrong password is still rejected", async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/login"))
        return { ok: false, status: 401, json: async () => ({}) };
      return {
        json: async () => ({
          "subsonic-response": {
            status: "failed",
            error: { code: 40, message: "Wrong username or password" },
          },
        }),
      };
    });

    const result = await signIn("user", "wrong");

    expect(result).toEqual({ ok: false, reason: "rejected", message: "" });
    expect(get(credentials).password).toBe("");
    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/"))).toBe(false);
  });

  it("publishes the management session only once the ping has passed", async () => {
    let keyAtPing = "unset";
    const base = server();
    globalThis.fetch = vi.fn(async (url, options) => {
      if (url.includes("/rest/ping")) keyAtPing = get(mumaApiKey);
      return base(url, options);
    });

    await signIn("user", "hunter2");

    expect(keyAtPing).toBe("");
    expect(get(mumaApiKey)).toBe("own-key-of-user");
  });

  it("a rejected ping publishes no management session", async () => {
    globalThis.fetch = server({ token: null, pingAccepts: () => false });

    const result = await signIn("user", "hunter2");

    expect(result.ok).toBe(false);
    expect(get(mumaApiKey)).toBe("");
    expect(get(mumaSessionActive)).toBe(false);
  });

  it("a token for another name is not used, and the sign-in fails", async () => {
    globalThis.fetch = server({ token: { username: "alice", token: "alices-token" } });

    const result = await signIn("user", "hunter2");

    expect(result.ok).toBe(false);
    expect(pings()).toHaveLength(0);
    expect(get(subsonicToken).token).toBe("");
  });

  it("an unreachable management API means offline, with no Subsonic request", async () => {
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) throw new TypeError("Failed to fetch");
      throw new Error(`unexpected ${url}`);
    });

    const result = await signIn("user", "hunter2");

    expect(result).toEqual({ ok: false, reason: "offline", message: "" });
    // Asked again before giving up, and never anything but MuMa's login.
    expect(globalThis.fetch).toHaveBeenCalledTimes(TOKEN_ATTEMPTS);
  });
});

/**
 * Without a token there is no sign-in (issue #72), so a busy token endpoint -- 503 while LMS's
 * database is locked, 404 for an account not synced yet -- is asked again before the sign-in
 * gives up; a refusal is not.
 */
describe("login - asking for the token more than once", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "", password: "" });
    subsonicToken.set({ username: "", token: "" });
    mumaApiKey.set("");
  });

  function server(tokenAnswers) {
    return vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) return { ok: true, json: async () => MUMA_ANSWER };
      if (url.includes("/api/auth/subsonic-token")) return tokenAnswers.shift()();
      return { json: async () => ({ "subsonic-response": { status: "ok" } }) };
    });
  }
  const busy = () => ({ ok: false, status: 503, json: async () => ({}) });
  const refused = () => ({ ok: false, status: 401, json: async () => ({}) });
  const token = () => ({
    ok: true,
    json: async () => ({ status: "ok", username: "user", token: "the-subsonic-token" }),
  });
  const tokenCalls = () =>
    globalThis.fetch.mock.calls.filter(([url]) => url.includes("/api/auth/subsonic-token")).length;

  it("signs in when the endpoint answers on a later attempt", async () => {
    globalThis.fetch = server([busy, token]);

    expect((await signIn("user", "hunter2")).ok).toBe(true);
    expect(tokenCalls()).toBe(2);
  });

  it("gives up as unreachable after the last attempt", async () => {
    globalThis.fetch = server(Array.from({ length: TOKEN_ATTEMPTS }, () => busy));

    expect(await signIn("user", "hunter2")).toEqual({ ok: false, reason: "offline", message: "" });
    expect(tokenCalls()).toBe(TOKEN_ATTEMPTS);
  });

  it("asks MuMa's login again when it was busy, not when it refused", async () => {
    let logins = 0;
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) {
        logins += 1;
        return logins === 1
          ? { ok: false, status: 503, json: async () => ({}) }
          : { ok: true, json: async () => MUMA_ANSWER };
      }
      if (url.includes("/api/auth/subsonic-token")) return token();
      return { json: async () => ({ "subsonic-response": { status: "ok" } }) };
    });

    expect((await signIn("user", "hunter2")).ok).toBe(true);
    expect(logins).toBe(2);
  });

  it("does not ask again after a refusal", async () => {
    globalThis.fetch = server([refused, token]);

    expect((await signIn("user", "hunter2")).reason).toBe("rejected");
    expect(tokenCalls()).toBe(1);
  });
});
