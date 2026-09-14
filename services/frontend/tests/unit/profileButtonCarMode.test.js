import { describe, it, expect, vi, afterEach } from "vitest";
import { render, fireEvent, screen } from "@testing-library/svelte";
import ProfileButton from "../../src/lib/ProfileButton.svelte";
import { platform } from "../../src/lib/platform/index.js";

/**
 * The overflow menu's "Carmodus" entry: native only, the same guard the device-settings tab
 * uses (`settingsNavigation.test.js`), because there is no car screen to open in a browser tab.
 */
function openMenu(container) {
  const toggle = container.querySelector("button");
  return fireEvent.click(toggle);
}

describe("ProfileButton car mode entry", () => {
  afterEach(() => {
    platform.system.isNative = false;
  });

  it("hides the entry outside a native shell", async () => {
    const { container } = render(ProfileButton, { onNavigate: vi.fn() });
    await openMenu(container);

    expect(screen.queryByText("Carmodus")).toBeNull();
  });

  it("offers the entry inside a native shell and navigates to it", async () => {
    platform.system.isNative = true;
    const onNavigate = vi.fn();
    const { container } = render(ProfileButton, { onNavigate });
    await openMenu(container);

    await fireEvent.click(screen.getByText("Carmodus"));

    expect(onNavigate).toHaveBeenCalledWith("car");
  });
});
