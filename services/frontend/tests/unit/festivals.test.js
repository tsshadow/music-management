import { describe, it, expect } from "vitest";
import {
  buildFestival,
  emptyFestival,
  filterFestivals,
  formFrom,
} from "../../src/lib/management/festivals.js";

describe("festival form", () => {
  it("round-trips a row through the form shape", () => {
    const form = formFrom({
      id: 1,
      name: "Defqon.1",
      active: true,
      aliases: ["Defqon 1"],
      editions: [{ year: 2025, date: "2025-06-27" }],
    });
    expect(form.aliasText).toBe("Defqon 1");
    expect(form.editions).toEqual([{ year: "2025", date: "2025-06-27" }]);
    const built = buildFestival(form);
    expect(built.valid).toBe(true);
    expect(built.payload).toEqual({
      name: "Defqon.1",
      active: true,
      aliases: ["Defqon 1"],
      editions: [{ year: 2025, date: "2025-06-27" }],
    });
  });

  it("starts empty and refuses to save without a name", () => {
    const built = buildFestival(formFrom(emptyFestival()));
    expect(built.valid).toBe(false);
    expect(built.error).toBe("management.festivals.errorName");
  });

  it("deduplicates aliases and drops blank lines", () => {
    const built = buildFestival({
      name: "Intents",
      aliasText: "Intents Festival\n\nintents festival\n Intents Fest ",
      editions: [],
    });
    expect(built.payload.aliases).toEqual(["Intents Festival", "Intents Fest"]);
  });

  it("checks editions and sorts them", () => {
    expect(
      buildFestival({ name: "X", editions: [{ year: "1970", date: "1970-01-01" }] }).error,
    ).toBe("management.festivals.errorYear");
    expect(
      buildFestival({ name: "X", editions: [{ year: "2025", date: "27-06-2025" }] }).error,
    ).toBe("management.festivals.errorDate");
    expect(
      buildFestival({
        name: "X",
        editions: [
          { year: "2025", date: "2025-06-27" },
          { year: "2025", date: "2025-06-28" },
        ],
      }).error,
    ).toBe("management.festivals.errorDuplicateYear");
    const built = buildFestival({
      name: "X",
      editions: [
        { year: "2025", date: "2025-06-27" },
        { year: "", date: "" },
        { year: "2024", date: "2024-06-28" },
      ],
    });
    expect(built.payload.editions.map((e) => e.year)).toEqual([2024, 2025]);
  });

  it("filters on name and alias", () => {
    const rows = [
      { name: "Defqon.1", aliases: ["Defqon 1"] },
      { name: "Karnaval Festival", aliases: [] },
    ];
    expect(filterFestivals(rows, "defqon 1").map((r) => r.name)).toEqual(["Defqon.1"]);
    expect(filterFestivals(rows, "karna").map((r) => r.name)).toEqual(["Karnaval Festival"]);
    expect(filterFestivals(rows, "")).toBe(rows);
  });
});
