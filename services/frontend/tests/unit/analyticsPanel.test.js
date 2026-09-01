import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import AnalyticsPanel from "../../src/lib/management/library/AnalyticsPanel.svelte";

function props(overrides = {}) {
  return {
    genreDistribution: [
      { genre: "Hardcore", state: "white", count: 1200 },
      { genre: "Tribecore", state: "unknown", count: 300 },
    ],
    bpmHistogram: [
      { bucket_start: 150, count: 40 },
      { bucket_start: 155, count: 120 },
    ],
    yearHistogram: [
      { year: 2023, count: 80 },
      { year: 2024, count: 160 },
    ],
    topArtists: [{ artist: "Angerfist", count: 210 }],
    topLabels: [{ label: "Roughstate", count: 95 }],
    bpmBucket: 5,
    onFilterAdd: vi.fn(),
    ...overrides,
  };
}

/** Fills the panel with data of one shape only, so a section can be checked empty. */
function only(section) {
  const empty = {
    genreDistribution: [],
    bpmHistogram: [],
    yearHistogram: [],
    topArtists: [],
    topLabels: [],
  };
  return props({ ...empty, ...section });
}

describe("AnalyticsPanel", () => {
  it("lists the genres with their track counts", () => {
    render(AnalyticsPanel, props());

    expect(screen.getByText("Hardcore")).toBeTruthy();
    expect(screen.getByText("1.200")).toBeTruthy();
  });

  it("marks a genre that has not been curated yet", () => {
    const { container } = render(AnalyticsPanel, props());

    const unknown = [...container.querySelectorAll("span")].find(
      (el) => el.textContent === "Tribecore",
    );
    expect(unknown.className).toContain("italic");
  });

  it("filters on the genre that was clicked", async () => {
    const onFilterAdd = vi.fn();
    render(AnalyticsPanel, props({ onFilterAdd }));

    await fireEvent.click(screen.getByText("Hardcore"));

    expect(onFilterAdd).toHaveBeenCalledWith("genre", "Hardcore");
  });

  it("filters on the artist that was clicked", async () => {
    const onFilterAdd = vi.fn();
    render(AnalyticsPanel, props({ onFilterAdd }));

    await fireEvent.click(screen.getByText("Angerfist"));

    expect(onFilterAdd).toHaveBeenCalledWith("artist", "Angerfist");
  });

  it("filters on the label that was clicked", async () => {
    const onFilterAdd = vi.fn();
    render(AnalyticsPanel, props({ onFilterAdd }));

    await fireEvent.click(screen.getByText("Roughstate"));

    expect(onFilterAdd).toHaveBeenCalledWith("label", "Roughstate");
  });

  it("labels the bpm axis with the range the buckets span", () => {
    render(AnalyticsPanel, props());

    expect(screen.getByText("150")).toBeTruthy();
    expect(screen.getByText("160")).toBeTruthy();
  });

  it("labels each bpm bar with its bucket and count", () => {
    render(AnalyticsPanel, props());

    expect(screen.getByText("155-160: 120")).toBeTruthy();
  });

  it("labels the year axis with the first and last year", () => {
    render(AnalyticsPanel, props());

    expect(screen.getByText("2023")).toBeTruthy();
    expect(screen.getByText("2024")).toBeTruthy();
  });

  it("scales every bar against the busiest bucket", () => {
    const { container } = render(AnalyticsPanel, props());

    const [first, second] = [...container.querySelectorAll(".h-48 > div")];
    expect(first.getAttribute("style")).toContain("height: 33.33");
    expect(second.getAttribute("style")).toContain("height: 100%");
  });

  it("warns that the bpm figures are a raw detection", () => {
    render(AnalyticsPanel, props());

    expect(screen.getByText(/Ruwe detectie/)).toBeTruthy();
  });

  it("says so per section when the selection holds nothing", () => {
    render(AnalyticsPanel, only({}));

    expect(screen.getByText("Geen genres in deze selectie.")).toBeTruthy();
    expect(screen.getByText("Geen BPM-data in deze selectie.")).toBeTruthy();
    expect(screen.getByText("Geen jaartallen in deze selectie.")).toBeTruthy();
    expect(screen.getByText("Geen artiesten in deze selectie.")).toBeTruthy();
    expect(screen.getByText("Geen labels in deze selectie.")).toBeTruthy();
  });

  it("still draws the sections that do have data", () => {
    render(AnalyticsPanel, only({ topArtists: [{ artist: "Angerfist", count: 210 }] }));

    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.queryByText("Geen artiesten in deze selectie.")).toBeNull();
  });
});
