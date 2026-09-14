import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import BottomSheetHost from "./fixtures/BottomSheetHost.svelte";

describe("BottomSheet", () => {
  afterEach(() => {
    document.body.style.overflow = "";
  });

  it("shows its title and content", () => {
    render(BottomSheetHost, { onclose: vi.fn(), title: "Genre" });

    expect(screen.getByText("Genre")).toBeTruthy();
    expect(screen.getByText("One")).toBeTruthy();
    expect(screen.getByText("Two")).toBeTruthy();
  });

  it("closes when the backdrop is clicked", async () => {
    const onclose = vi.fn();
    render(BottomSheetHost, { onclose });

    // The backdrop is the first of the two buttons the sheet itself renders
    // (backdrop, then the header's close button); the option buttons come
    // from the host's own content.
    await fireEvent.click(screen.getByLabelText("Paneel sluiten"));

    expect(onclose).toHaveBeenCalled();
  });

  it("closes on the header close button", async () => {
    const onclose = vi.fn();
    render(BottomSheetHost, { onclose });

    await fireEvent.click(screen.getByLabelText("Sluiten"));

    expect(onclose).toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    const onclose = vi.fn();
    render(BottomSheetHost, { onclose });

    await fireEvent.keyDown(window, { key: "Escape" });

    expect(onclose).toHaveBeenCalled();
  });

  it("reports a picked option", async () => {
    const onselect = vi.fn();
    render(BottomSheetHost, { onclose: vi.fn(), onselect });

    await fireEvent.click(screen.getByText("Two"));

    expect(onselect).toHaveBeenCalledWith("Two");
  });

  it("locks page scroll while open and restores it once closed", async () => {
    const { unmount } = render(BottomSheetHost, { onclose: vi.fn() });

    expect(document.body.style.overflow).toBe("hidden");

    unmount();

    await waitFor(() => expect(document.body.style.overflow).toBe(""));
  });

  it("traps Tab within the sheet, not out to the backdrop", async () => {
    render(BottomSheetHost, { onclose: vi.fn(), options: ["Only"] });

    // The backdrop is its own full-screen button outside the sheet card, so
    // the trap's "first" element is the header's close button, not it.
    const backdrop = screen.getByLabelText("Paneel sluiten");
    const closeButton = screen.getByLabelText("Sluiten");
    const last = screen.getByText("Only");

    last.focus();
    expect(document.activeElement).toBe(last);

    await fireEvent.keyDown(window, { key: "Tab" });

    expect(document.activeElement).toBe(closeButton);
    expect(document.activeElement).not.toBe(backdrop);
  });
});
