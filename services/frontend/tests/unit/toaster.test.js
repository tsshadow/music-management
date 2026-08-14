import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import Toaster from "../../src/lib/Toaster.svelte";
import { notify, dismissAll, notifications } from "../../src/lib/notifications.js";
import { isMobile } from "../../src/lib/store.js";

describe("Toaster", () => {
  beforeEach(() => {
    dismissAll();
    isMobile.set(false);
  });

  afterEach(() => {
    dismissAll();
    vi.restoreAllMocks();
  });

  it("shows nothing while there are no notifications", () => {
    render(Toaster);

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows the message of an error", async () => {
    render(Toaster);

    notify.error("Beoordeling kon niet worden opgeslagen");

    expect(await screen.findByText("Beoordeling kon niet worden opgeslagen")).toBeInTheDocument();
  });

  it("shows the detail line under the message", async () => {
    render(Toaster);

    notify.warning("Scrobble mislukt", { detail: "HTTP 503" });

    expect(await screen.findByText("HTTP 503")).toBeInTheDocument();
  });

  // A failure has to interrupt the screen reader; a confirmation must not.
  it("announces an error assertively and a success politely", async () => {
    render(Toaster);

    notify.error("Kapot");
    notify.success("Gelukt");

    expect(await screen.findByRole("alert")).toHaveTextContent("Kapot");
    expect(await screen.findByRole("status")).toHaveTextContent("Gelukt");
  });

  it("the close button removes that notification", async () => {
    render(Toaster);
    notify.error("Beoordeling kon niet worden opgeslagen");
    await screen.findByText("Beoordeling kon niet worden opgeslagen");

    await fireEvent.click(screen.getByLabelText("Sluiten"));

    expect(screen.queryByText("Beoordeling kon niet worden opgeslagen")).toBeNull();
  });

  it('offers "clear all" only above one notification', async () => {
    render(Toaster);

    notify.error("een");
    await screen.findByText("een");
    expect(screen.queryByText("Alles wissen")).toBeNull();

    notify.error("twee");
    await screen.findByText("twee");
    await fireEvent.click(screen.getByText("Alles wissen"));

    expect(screen.queryByText("een")).toBeNull();
    expect(screen.queryByText("twee")).toBeNull();
  });

  it("shows how often a repeated notification happened", async () => {
    render(Toaster);

    notify.error("Beoordeling kon niet worden opgeslagen");
    notify.error("Beoordeling kon niet worden opgeslagen");

    expect(await screen.findByText("2×")).toBeInTheDocument();
  });

  it("holds the countdown while the pointer is over the stack", async () => {
    render(Toaster);
    notify.info("Blijf staan");
    const stack = await screen.findByRole("region", { name: "Meldingen" });

    await fireEvent.mouseEnter(stack);
    expect(get(notifications)).toHaveLength(1);

    await fireEvent.mouseLeave(stack);
    expect(get(notifications)).toHaveLength(1);
  });
});
