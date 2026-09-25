import { describe, it, expect } from "vitest";
import { createRadioStartGuard } from "../../src/lib/radioStartGuard.js";

describe("createRadioStartGuard", () => {
  it("drops a repeat of the start already in flight", () => {
    const guard = createRadioStartGuard();

    const first = guard.begin("main");
    expect(first).not.toBeNull();
    expect(guard.begin("main")).toBeNull();
    expect(first.isCurrent()).toBe(true);
  });

  it("lets the same channel start again once the first attempt is done", () => {
    const guard = createRadioStartGuard();

    guard.begin("main").done();

    expect(guard.begin("main")).not.toBeNull();
  });

  it("a newer start makes the older ticket stale", () => {
    const guard = createRadioStartGuard();

    const main = guard.begin("main");
    const other = guard.begin("other");

    expect(main.isCurrent()).toBe(false);
    expect(other.isCurrent()).toBe(true);
    // The stale ticket finishing must not clear the newer one's duplicate check.
    main.done();
    expect(guard.pending()).toBe("other");
    expect(guard.begin("other")).toBeNull();
  });

  it("invalidate makes every outstanding ticket stale, as switching radio off does", () => {
    const guard = createRadioStartGuard();

    const main = guard.begin("main");
    guard.invalidate();

    expect(main.isCurrent()).toBe(false);
    expect(guard.pending()).toBeNull();
    expect(guard.begin("main")).not.toBeNull();
  });

  it("without a key there is no duplicate check, only the newest-wins rule", () => {
    const guard = createRadioStartGuard();

    const a = guard.begin();
    const b = guard.begin();

    expect(a.isCurrent()).toBe(false);
    expect(b.isCurrent()).toBe(true);
  });
});
