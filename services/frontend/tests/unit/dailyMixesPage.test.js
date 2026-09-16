/**
 * The phone's own "Daily mixes" page, reached from the Home tile.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

import DailyMixesPage from "../../src/lib/DailyMixesPage.svelte";
import { credentials } from "../../src/lib/store.js";

const CARDS = [
  {
    slug: "daily-mix-soft",
    title: "Zachter",
    subtitle: "≤ 42 hardheid",
    color: "#1DB954",
    cover: null,
  },
  {
    slug: "daily-mix-mid",
    title: "Middenin",
    subtitle: "42–70 hardheid",
    color: "#2D5AFC",
    cover: null,
  },
  {
    slug: "daily-mix-hard",
    title: "Harder",
    subtitle: "≥ 70 hardheid",
    color: "#E23744",
    cover: null,
  },
  {
    slug: "daily-mix-artist",
    title: "Angerfist",
    subtitle: "Een artiest uit jouw top 10",
    color: "#E13300",
    cover: null,
  },
  {
    slug: "daily-mix-label",
    title: "Neophyte Records",
    subtitle: "Een label uit jouw top 10",
    color: "#7358FF",
    cover: null,
  },
];

vi.mock("../../src/lib/dailyMixes.js", () => ({
  loadDailyMixCards: (...args) => globalThis.__loadDailyMixCards(...args),
}));

vi.mock("../../src/lib/genreTints.js", () => ({
  fetchGenreTints: async () => ({}),
}));

describe("DailyMixesPage", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    globalThis.__loadDailyMixCards = vi.fn(async () => CARDS);
  });

  it("shows a loading state before the cards answer", () => {
    globalThis.__loadDailyMixCards = vi.fn(() => new Promise(() => {}));

    render(DailyMixesPage, { onnavigate: vi.fn() });

    expect(screen.getByText("Laden...")).toBeTruthy();
  });

  it("lists all five mixes", async () => {
    render(DailyMixesPage, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Zachter")).toBeTruthy());
    for (const card of CARDS) expect(screen.getByText(card.title)).toBeTruthy();
  });

  it("opens a mix's own page when tapped", async () => {
    const onnavigate = vi.fn();
    render(DailyMixesPage, { onnavigate });

    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: /Angerfist/ }));

    expect(onnavigate).toHaveBeenCalledWith("daily-mix-artist");
  });
});
