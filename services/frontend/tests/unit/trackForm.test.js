import { describe, expect, it } from "vitest";

import { FORM_LABEL_KEYS, SET_FORMS, TRACK_FORMS, formParam } from "../../src/lib/trackForm.js";

describe("trackForm", () => {
  it("mirrors the four forms the backend classifies", () => {
    expect(TRACK_FORMS).toEqual(["track", "set", "liveset", "podcast"]);
  });

  it("offers only the long forms in the sets view", () => {
    expect(SET_FORMS).toEqual(["set", "liveset", "podcast"]);
    for (const form of TRACK_FORMS) expect(FORM_LABEL_KEYS[form]).toBe(`filter.form.${form}`);
  });

  it("sends a form only in the sets view", () => {
    expect(formParam("liveset", "sets")).toBe("liveset");
    expect(formParam("liveset", "songs")).toBeUndefined();
  });

  it("sends nothing for no selection or a value that is not a set form", () => {
    expect(formParam("", "sets")).toBeUndefined();
    expect(formParam(null, "sets")).toBeUndefined();
    expect(formParam("track", "sets")).toBeUndefined();
    expect(formParam("mixtape", "sets")).toBeUndefined();
    expect(formParam(" Podcast ", "sets")).toBe("podcast");
  });
});
