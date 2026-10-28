// The seeded stand-in for the lazily loaded artist and album pages (issue #118): the heading the
// optimistic navigation of #107 promises must be on screen before the page's chunk is.
import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/svelte";
import EntityPageShell from "../../src/lib/EntityPageShell.svelte";
import { clearSeeds, seedEntity } from "../../src/lib/entitySeeds.js";
import { credentials } from "../../src/lib/store.js";

describe("EntityPageShell", () => {
  beforeEach(() => {
    clearSeeds();
    credentials.set({ url: "", username: "demo-user", password: "pw" });
  });

  it("draws an artist's seeded name as the heading, with skeleton rows below", () => {
    seedEntity("artist", "ar-1", { name: "Angerfist" });

    render(EntityPageShell, { props: { kind: "artist", id: "ar-1" } });

    expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Angerfist" }).getAttribute("src")).toContain(
      "/api/artists/Angerfist/image",
    );
  });

  it("draws an album's seeded title and cover", () => {
    seedEntity("album", "al-1", { name: "Mutilate", coverArt: "al-1" });

    render(EntityPageShell, { props: { kind: "album", id: "al-1" } });

    expect(screen.getByRole("heading", { level: 1, name: "Mutilate" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Mutilate" }).getAttribute("src")).toContain(
      "getCoverArt?id=al-1",
    );
  });

  it("without a seed shows skeletons, never a heading", () => {
    render(EntityPageShell, { props: { kind: "artist", id: "unknown" } });

    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
  });
});
