// A lazily loaded part rendered with `bind:` props (issue #118): `lazyComponent.svelte.js`.
import { describe, it, expect, vi } from "vitest";
import { createLazyRegistry } from "../../src/lib/lazyViews.js";
import { lazyComponent } from "../../src/lib/lazyComponent.svelte.js";

describe("lazyComponent", () => {
  it("is null until loaded, then the component; a second load fetches nothing", async () => {
    const loader = vi.fn(() => Promise.resolve({ default: "FilterBar" }));
    const part = lazyComponent(createLazyRegistry({ filterBar: loader }), "filterBar");

    expect(part.current).toBeNull();
    part.load();
    part.load();
    await vi.waitFor(() => expect(part.current).toBe("FilterBar"));
    part.load();

    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("is there at once when the chunk already is (the boot or idle preload)", async () => {
    const registry = createLazyRegistry({ bar: () => Promise.resolve({ default: "Bar" }) });
    await registry.load("bar");

    expect(lazyComponent(registry, "bar").current).toBe("Bar");
  });

  it("logs a failed fetch and tries again on the next load", async () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({ default: "Grid" });
    const part = lazyComponent(createLazyRegistry({ grid: loader }), "grid");

    part.load();
    await vi.waitFor(() => expect(error).toHaveBeenCalled());
    expect(part.current).toBeNull();
    part.load();
    await vi.waitFor(() => expect(part.current).toBe("Grid"));

    expect(loader).toHaveBeenCalledTimes(2);
    error.mockRestore();
  });
});
