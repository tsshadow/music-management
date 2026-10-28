import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import Advanced from "../../src/lib/settings/Advanced.svelte";
import { credentials, visibleSortOptions } from "../../src/lib/store.js";

const DEFAULT_SORT_OPTIONS = {
  songs: ["recent", "added", "mostplayed", "recentlyplayed", "rating", "alpha", "random"],
  albums: ["newest", "recent", "alphabeticalByName", "alphabeticalByArtist", "random", "starred"],
  artists: ["alphabetical", "trackCount", "newest", "recent", "starred", "random"],
};

function subsonic(status) {
  return vi.fn(async () => ({ json: async () => ({ "subsonic-response": { status } }) }));
}

async function submitPassword(newPassword, confirmation = newPassword) {
  await fireEvent.input(screen.getByLabelText("Nieuw Wachtwoord"), {
    target: { value: newPassword },
  });
  await fireEvent.input(screen.getByLabelText("Bevestig Wachtwoord"), {
    target: { value: confirmation },
  });
  await fireEvent.click(screen.getByText("Wachtwoord Bijwerken"));
}

describe("Advanced settings", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    visibleSortOptions.set(structuredClone(DEFAULT_SORT_OPTIONS));
    globalThis.fetch = subsonic("ok");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("refuses two passwords that do not match", async () => {
    render(Advanced);

    await submitPassword("hardcore", "uptempo");

    expect(screen.getByText("Wachtwoorden komen niet overeen")).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("refuses a password that is too short", async () => {
    render(Advanced);

    await submitPassword("abc");

    expect(screen.getByText("Wachtwoord moet minimaal 4 tekens bevatten")).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("sends the new password for the logged-in user and clears the fields", async () => {
    render(Advanced);

    await submitPassword("hardcore");

    await waitFor(() => expect(screen.getByText("Wachtwoord succesvol gewijzigd!")).toBeTruthy());
    const url = globalThis.fetch.mock.calls[0][0];
    expect(url).toContain("/rest/updateUser?");
    expect(url).toContain("username=demo-user");
    expect(url).toContain("password=hardcore");
    expect(screen.getByLabelText("Nieuw Wachtwoord").value).toBe("");
    expect(screen.getByLabelText("Bevestig Wachtwoord").value).toBe("");
  });

  it("reports a server that refused the change", async () => {
    globalThis.fetch = subsonic("failed");
    render(Advanced);

    await submitPassword("hardcore");

    await waitFor(() => expect(screen.getByText("Fout bij wijzigen wachtwoord")).toBeTruthy());
    expect(screen.getByLabelText("Nieuw Wachtwoord").value).toBe("hardcore");
  });

  it("reports a change that never reached the server", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    render(Advanced);

    await submitPassword("hardcore");

    await waitFor(() => expect(screen.getByText("Netwerkfout")).toBeTruthy());
  });

  it("cannot submit an empty password", () => {
    render(Advanced);

    expect(screen.getByText("Wachtwoord Bijwerken").disabled).toBe(true);
  });

  it("ticks the sort options that are currently visible", () => {
    render(Advanced);

    const checked = screen.getAllByRole("checkbox").filter((box) => box.checked);
    const total = Object.values(DEFAULT_SORT_OPTIONS).reduce((sum, list) => sum + list.length, 0);
    expect(checked).toHaveLength(total);
  });

  it("hides a sort option that is unticked", async () => {
    render(Advanced);

    await fireEvent.click(screen.getAllByRole("checkbox")[0]);

    expect(get(visibleSortOptions).songs).not.toContain("recent");
  });

  it("shows a sort option again when it is ticked", async () => {
    visibleSortOptions.set({ ...structuredClone(DEFAULT_SORT_OPTIONS), songs: [] });
    render(Advanced);

    await fireEvent.click(screen.getAllByRole("checkbox")[0]);

    expect(get(visibleSortOptions).songs).toEqual(["recent"]);
  });

  it("groups the options per library section", () => {
    render(Advanced);

    expect(screen.getByText("Nummers")).toBeTruthy();
    expect(screen.getByText("Albums")).toBeTruthy();
    expect(screen.getByText("Artiesten")).toBeTruthy();
  });
});
