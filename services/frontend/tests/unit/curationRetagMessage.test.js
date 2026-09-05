import { describe, expect, it } from "vitest";

import { marked } from "../../src/lib/curation/curationApi.js";

/**
 * The count in this message is the whole point of the change it belongs to: a rule that
 * saved but queued nothing used to read exactly like one that saved and would apply.
 */
describe("marked", () => {
  it("names how many files were queued", () => {
    expect(marked({ marked_for_retag: 143 }, "Regel opgeslagen.")).toBe(
      "Regel opgeslagen. 143 bestanden staan in de wachtrij om opnieuw getagd te worden.",
    );
  });

  it("says so when nothing was queued", () => {
    expect(marked({ marked_for_retag: 0 }, "Regel opgeslagen.")).toBe(
      "Regel opgeslagen. Geen bestanden gevonden om opnieuw te taggen.",
    );
  });

  it("counts one file in the singular", () => {
    expect(marked({ marked_for_retag: 1 }, "Regel verwijderd.")).toContain("1 bestand staat");
  });

  it("survives a server that does not report the count yet", () => {
    expect(marked({ status: "ok" }, "Regel opgeslagen.")).toBe(
      "Regel opgeslagen. Geen bestanden gevonden om opnieuw te taggen.",
    );
    expect(marked(undefined, "Regel opgeslagen.")).toContain("Regel opgeslagen.");
  });
});
