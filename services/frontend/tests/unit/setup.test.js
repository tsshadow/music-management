import { describe, it, expect } from "vitest";
import { SETUP_STEPS, allSteps, isUpdateRun, markSeen, pendingSteps } from "../../src/lib/setup.js";

const NATIVE = { storage: { supported: true } };
const BROWSER = { storage: { supported: false } };

describe("setup steps", () => {
  it("has permanent, unique ids", () => {
    const ids = SETUP_STEPS.map((step) => step.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("walks every step on a first run", () => {
    expect(pendingSteps([], NATIVE)).toEqual(SETUP_STEPS);
  });

  it("copes with a seen list that is not a list", () => {
    expect(pendingSteps(undefined, NATIVE)).toEqual(SETUP_STEPS);
    expect(pendingSteps("language", NATIVE)).toEqual(SETUP_STEPS);
  });

  it("walks only the steps the account has not been through", () => {
    const seen = SETUP_STEPS.map((step) => step.id).filter((id) => id !== "home");

    expect(pendingSteps(seen, NATIVE).map((step) => step.id)).toEqual(["home"]);
  });

  it("walks nothing once every step is seen", () => {
    expect(
      pendingSteps(
        SETUP_STEPS.map((step) => step.id),
        NATIVE,
      ),
    ).toEqual([]);
  });

  it("keeps the downloads step out of a browser", () => {
    const ids = pendingSteps([], BROWSER).map((step) => step.id);
    expect(ids).not.toContain("downloads");
    expect(pendingSteps([], undefined).map((step) => step.id)).not.toContain("downloads");
    expect(allSteps(NATIVE).map((step) => step.id)).toContain("downloads");
  });

  it("calls a run an update once anything was seen before", () => {
    expect(isUpdateRun([])).toBe(false);
    expect(isUpdateRun(undefined)).toBe(false);
    expect(isUpdateRun(["language"])).toBe(true);
  });

  it("records the walked steps on top of the seen ones, once each", () => {
    expect(markSeen(["language"], [{ id: "language" }, { id: "mode" }])).toEqual([
      "language",
      "mode",
    ]);
    expect(markSeen(undefined, [{ id: "guide" }])).toEqual(["guide"]);
  });
});
