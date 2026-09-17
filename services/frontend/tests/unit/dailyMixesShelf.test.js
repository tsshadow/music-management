/**
 * The Home row of five daily-mix cards, shared by the desktop shelf and the phone's own
 * "Overzicht" mode.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

import DailyMixesShelf from "../../src/lib/DailyMixesShelf.svelte";
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

describe("DailyMixesShelf", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    globalThis.__loadDailyMixCards = vi.fn(async () => ({ cards: CARDS, refine: vi.fn() }));
  });

  it("shows the heading and the five cards", async () => {
    render(DailyMixesShelf, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Zachter")).toBeTruthy());
    expect(screen.getByRole("heading", { name: "Dagelijkse mixen" })).toBeTruthy();
    for (const card of CARDS) expect(screen.getByText(card.title)).toBeTruthy();
  });

  it("always renders its own heading, even before the cards have loaded", () => {
    globalThis.__loadDailyMixCards = vi.fn(() => new Promise(() => {}));

    render(DailyMixesShelf, { onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { name: "Dagelijkse mixen" })).toBeTruthy();
  });

  it("renders cards while refinements wait and replaces a card when one arrives", async () => {
    let publish;
    globalThis.__loadDailyMixCards = vi.fn(async () => ({
      cards: CARDS,
      refine: (onRefine) => {
        publish = onRefine;
        return new Promise(() => {});
      },
    }));
    render(DailyMixesShelf, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Zachter")).toBeTruthy());
    publish({ ...CARDS[0], title: "Refined mix", color: "#FF00AA" });
    await waitFor(() => expect(screen.getByText("Refined mix")).toBeTruthy());
    expect(screen.queryByText("Zachter")).toBeNull();
  });

  it("opens the mix that was tapped", async () => {
    const onnavigate = vi.fn();
    render(DailyMixesShelf, { onnavigate });

    await waitFor(() => expect(screen.getByText("Harder")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: /Harder/ }));

    expect(onnavigate).toHaveBeenCalledWith("daily-mix-hard");
  });
});
