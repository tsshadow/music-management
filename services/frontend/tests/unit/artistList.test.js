import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import ArtistList from "../../src/lib/ArtistList.svelte";

describe("ArtistList", () => {
  it("navigates to the artist when its name is tapped", async () => {
    const onnavigate = vi.fn();
    render(ArtistList, { artist: "Angerfist", artistId: "a1", onnavigate });

    await screen.getByText("Angerfist").click();

    expect(onnavigate).toHaveBeenCalledWith("artist:a1");
  });

  it("gives every artist in a multi-artist list its own tap target", async () => {
    const onnavigate = vi.fn();
    render(ArtistList, {
      artists: [
        { id: "a1", name: "Headhunterz" },
        { id: "a2", name: "Wildstylez" },
      ],
      onnavigate,
    });

    await screen.getByText("Wildstylez").click();

    expect(onnavigate).toHaveBeenCalledWith("artist:a2");
  });

  it("shows no chevron in the default small size", () => {
    render(ArtistList, { artist: "Angerfist", artistId: "a1" });

    expect(document.querySelector("svg")).toBeNull();
  });

  it("adds a trailing chevron in the lg size once an artist has an id", () => {
    render(ArtistList, { artist: "Angerfist", artistId: "a1", size: "lg" });

    expect(document.querySelector("svg")).toBeTruthy();
  });

  it("omits the chevron in the lg size when no artist has an id", () => {
    render(ArtistList, { artist: "Unknown Artist", artistId: null, size: "lg" });

    expect(document.querySelector("svg")).toBeNull();
  });

  it("gives the lg size a taller, roomier row", () => {
    render(ArtistList, { artist: "Angerfist", artistId: "a1", size: "lg" });

    const row = screen.getByText("Angerfist").closest("span[class*='min-h-11']");
    expect(row).toBeTruthy();
  });

  it("separates the names with a comma and a space", () => {
    render(ArtistList, {
      artists: [
        { id: "a1", name: "Catscan" },
        { id: "a2", name: "Starving Insect" },
      ],
    });

    expect(screen.getByText("Catscan").parentElement.textContent).toBe("Catscan, Starving Insect");
  });

  it("keeps several artists on one truncating line in the large size", () => {
    // As direct flex items, every name and every ", " became its own column, and
    // four artists wrapped into a ragged block on the player ("David / Levy").
    render(ArtistList, {
      artists: [
        { id: "a1", name: "Audiofreq" },
        { id: "a2", name: "David Levy" },
        { id: "a3", name: "Sovereign King" },
      ],
      size: "lg",
      onnavigate: vi.fn(),
    });

    const row = screen.getByTestId("artist-list-lg");
    const names = screen.getByText("David Levy").parentElement;
    expect(names.parentElement).toBe(row);
    expect(names.className).toContain("truncate");
    expect(names.textContent.replace(/\s+/g, " ").trim()).toBe(
      "Audiofreq, David Levy, Sovereign King",
    );
  });
});
