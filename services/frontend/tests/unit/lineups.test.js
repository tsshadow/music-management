import { describe, it, expect } from "vitest";
import {
  buildLineup,
  fieldsFromId,
  groupByFestival,
  replaceName,
} from "../../src/lib/management/lineups.js";

describe("lineups helpers", () => {
  it("groups files by festival, keeping order", () => {
    const groups = groupByFestival([
      { id: "Defqon.1/2014/RED", festival: "Defqon.1" },
      { id: "Defqon.1/2015", festival: "Defqon.1" },
      { id: "Intents 2025", festival: "Intents 2025" },
    ]);
    expect(groups.map((g) => [g.festival, g.lineups.length])).toEqual([
      ["Defqon.1", 2],
      ["Intents 2025", 1],
    ]);
  });

  it("splits an id into the editor fields", () => {
    expect(fieldsFromId("Defqon.1/2014/RED")).toEqual({
      festival: "Defqon.1",
      year: "2014",
      stage: "RED",
    });
    expect(fieldsFromId("Intents 2025")).toEqual({ festival: "Intents 2025", year: "", stage: "" });
  });

  it("validates the editor the way the API does", () => {
    expect(buildLineup({ festival: "", text: "x" }).error).toBe("management.lineups.errorFestival");
    expect(buildLineup({ festival: "D", year: "25", text: "x" }).error).toBe(
      "management.lineups.errorYear",
    );
    expect(buildLineup({ festival: "D", stage: "RED", text: "x" }).error).toBe(
      "management.lineups.errorStageWithoutYear",
    );
    expect(buildLineup({ festival: "D", year: "2025", text: " \n" }).error).toBe(
      "management.lineups.errorEmpty",
    );
    expect(
      buildLineup({ festival: " Defqon.1 ", year: "2025", stage: " RED ", text: "Angerfist\n" })
        .payload,
    ).toEqual({
      festival: "Defqon.1",
      year: 2025,
      stage: "RED",
      text: "Angerfist\n",
    });
  });

  it("replaces one typed line by the library's spelling", () => {
    expect(
      replaceName(
        "Angerfist\nd-block and s-te-fan\nMiss K8",
        "D-Block and S-te-fan",
        "D-Block & S-te-Fan",
      ),
    ).toBe("Angerfist\nD-Block & S-te-Fan\nMiss K8");
  });
});
