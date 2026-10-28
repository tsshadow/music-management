import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import LibrariesTab from "../../src/lib/management/tabs/LibrariesTab.svelte";
import { credentials, subsonicToken } from "../../src/lib/store.js";

const LIBRARIES = [
  { id: 1, name: "Muziek", path: "/music" },
  { id: 2, name: "Labels", path: "/music/labels" },
];

function props(overrides = {}) {
  return { onMessage: () => {}, onError: () => {}, ...overrides };
}

describe("LibrariesTab", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => LIBRARIES,
      text: async () => "",
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the libraries with their on-disk path", async () => {
    render(LibrariesTab, props());

    await waitFor(() => expect(screen.getByText("Muziek")).toBeTruthy());
    expect(screen.getByText("/music")).toBeTruthy();
    expect(screen.getByText("/music/labels")).toBeTruthy();
  });

  it("authenticates the admin call with Subsonic credentials", async () => {
    render(LibrariesTab, props());

    await waitFor(() => expect(screen.getByText("Muziek")).toBeTruthy());
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain("/api/admin/libraries");
    expect(url).toContain("u=demo-user");
  });

  it("deletes a library after confirmation", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onMessage = vi.fn();

    render(LibrariesTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("Muziek")).toBeTruthy());

    await fireEvent.click(screen.getAllByText("Verwijderen")[0]);

    await waitFor(() => {
      const del = globalThis.fetch.mock.calls.find((c) => c[1]?.method === "DELETE");
      expect(del).toBeTruthy();
      expect(del[0]).toContain("/api/admin/libraries/1");
    });
    expect(onMessage).toHaveBeenCalled();
  });

  it("does not delete when the confirmation is dismissed", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(LibrariesTab, props());
    await waitFor(() => expect(screen.getByText("Muziek")).toBeTruthy());

    await fireEvent.click(screen.getAllByText("Verwijderen")[0]);

    expect(globalThis.fetch.mock.calls.some((c) => c[1]?.method === "DELETE")).toBe(false);
  });

  it("explains itself instead of silently failing without server credentials", async () => {
    credentials.set({ url: "", username: "", password: "" });

    render(LibrariesTab, props());

    await waitFor(() => expect(screen.getByText("Geen serververbinding")).toBeTruthy());
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
