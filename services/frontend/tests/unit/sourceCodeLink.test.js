import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/svelte";

import LoginPage from "../../src/lib/LoginPage.svelte";
import SourceCodeLink from "../../src/lib/SourceCodeLink.svelte";
import { fetchSourceUrl, safeSourceUrl } from "../../src/lib/sourceLink.js";
import { setLocaleFromAccount } from "../../src/lib/i18n/index.js";

describe("safeSourceUrl", () => {
  it("keeps http and https in any case, trimmed", () => {
    expect(safeSourceUrl(" HTTPS://git.example/x ")).toBe("HTTPS://git.example/x");
    expect(safeSourceUrl("http://git.example")).toBe("http://git.example");
  });

  it.each([
    "javascript:alert(1)",
    "intent://x",
    "data:text/html,x",
    "//git.example",
    "https://a@evil.example",
    "https://a:b@x.example",
    "https:///path",
    "https://",
    "",
    null,
    5,
  ])("drops %s", (value) => expect(safeSourceUrl(value)).toBe(""));
});

describe("fetchSourceUrl", () => {
  afterEach(() => vi.restoreAllMocks());

  it("reads the address, also from a 503 body", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({ source_url: "https://git.example/muma" }),
    }));
    expect(await fetchSourceUrl("https://api.example")).toBe("https://git.example/muma");
    expect(globalThis.fetch).toHaveBeenCalledWith("https://api.example/health", expect.anything());
  });

  it("gives an empty string when the request does not answer within the timeout", async () => {
    globalThis.fetch = vi.fn(
      (_url, { signal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener("abort", () => reject(new Error("aborted")));
        }),
    );
    expect(await fetchSourceUrl("https://api.example", { timeoutMs: 20 })).toBe("");
  });

  it("does not fetch a relative /health in the native shell without an API base", async () => {
    globalThis.fetch = vi.fn();
    expect(await fetchSourceUrl("", { native: true })).toBe("");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("still fetches a relative /health in a browser, where the origin is the server", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ source_url: "https://git.example/x" }),
    }));
    expect(await fetchSourceUrl("")).toBe("https://git.example/x");
  });

  it("gives an empty string when the request fails", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("offline");
    });
    expect(await fetchSourceUrl("https://api.example")).toBe("");
  });
});

describe("SourceCodeLink", () => {
  afterEach(cleanup);

  it("renders a link", () => {
    setLocaleFromAccount("nl");
    render(SourceCodeLink, { props: { url: "https://git.example/muma" } });
    const link = screen.getByRole("link", { name: "Broncode" });
    expect(link).toHaveAttribute("href", "https://git.example/muma");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders nothing for a hostile value", () => {
    render(SourceCodeLink, { props: { url: "javascript:alert(1)" } });
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("opens through the shell in the app", async () => {
    const openUrl = vi.fn(async () => {});
    render(SourceCodeLink, {
      props: { url: "https://git.example/muma", platform: { system: { isNative: true, openUrl } } },
    });
    await fireEvent.click(screen.getByTestId("source-link"));
    expect(openUrl).toHaveBeenCalledWith("https://git.example/muma");
  });
});

describe("LoginPage source link", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("offers the source before sign-in", async () => {
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () =>
        String(url).endsWith("/health") ? { source_url: "https://git.example/muma" } : {},
    }));
    render(LoginPage);
    const link = await screen.findByTestId("source-link");
    expect(link).toHaveAttribute("href", "https://git.example/muma");
  });

  it("shows no link when /health reports a hostile value", async () => {
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () =>
        String(url).endsWith("/health") ? { source_url: "javascript:alert(1)" } : {},
    }));
    render(LoginPage);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    // Let fetchSourceUrl resolve and the component re-render before asserting an absence.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("source-link")).toBeNull();
  });

  it("shows the link in the same flow for a safe value, so the absence above means something", async () => {
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () =>
        String(url).endsWith("/health") ? { source_url: "https://git.example/ok" } : {},
    }));
    render(LoginPage);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByTestId("source-link")).toBeTruthy();
  });
});
