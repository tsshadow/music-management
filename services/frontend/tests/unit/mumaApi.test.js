import { afterEach, describe, expect, it, vi } from "vitest";

import { MumaHttpError, fetchMumaJson } from "../../src/lib/mumaApi.js";

/**
 * `fetchMumaJson` used to return whatever JSON came back, success or not. A `{"detail": ...}` from
 * a 401 or a 500 then reached callers as data: `listFeeds` cached it as "no feeds" for the session
 * and the management page assigned it into its user and account lists.
 */

/** A fetch answering once with `status` and `body` (or a body that is not JSON). */
function answering(status, body) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new SyntaxError("Unexpected token <");
      return body;
    },
  }));
}

describe("fetchMumaJson", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the parsed body of a successful answer", async () => {
    globalThis.fetch = answering(200, { feeds: [] });

    await expect(fetchMumaJson("https://muma.example/api/feeds")).resolves.toEqual({ feeds: [] });
  });

  it("throws a MumaHttpError on a non-2xx answer, even when its body is JSON", async () => {
    globalThis.fetch = answering(401, { detail: "Not authenticated" });

    const error = await fetchMumaJson("https://muma.example/api/users").catch((e) => e);

    expect(error).toBeInstanceOf(MumaHttpError);
    expect(error.status).toBe(401);
    // The body travels with the error, for a caller that can still use it (/health's 503).
    expect(error.body).toEqual({ detail: "Not authenticated" });
  });

  it("throws a MumaHttpError without a body when the error page is not JSON", async () => {
    globalThis.fetch = answering(500, undefined);

    const error = await fetchMumaJson("https://muma.example/api/config").catch((e) => e);

    expect(error).toBeInstanceOf(MumaHttpError);
    expect(error.status).toBe(500);
    expect(error.body).toBeNull();
  });

  it("still names the status when a successful answer is not JSON", async () => {
    globalThis.fetch = answering(200, undefined);

    await expect(fetchMumaJson("https://muma.example/api/config")).rejects.toThrow(/200/);
  });
});
