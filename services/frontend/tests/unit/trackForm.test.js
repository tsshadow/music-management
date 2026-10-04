import { describe, expect, it } from "vitest";

import {
  FORM_LABEL_KEYS,
  NON_MUSIC_FORMS,
  SET_FORMS,
  TRACK_FORMS,
  formParam,
} from "../../src/lib/trackForm.js";

describe("trackForm", () => {
  it("mirrors the six forms the backend classifies", () => {
    expect(TRACK_FORMS).toEqual(["track", "set", "liveset", "podcast", "interview", "preview"]);
  });

  it("offers only the long forms in the sets view", () => {
    expect(SET_FORMS).toEqual(["set", "liveset", "podcast"]);
    for (const form of TRACK_FORMS) expect(FORM_LABEL_KEYS[form]).toBe(`filter.form.${form}`);
  });

  it("never offers or sends a non-music form", () => {
    expect(NON_MUSIC_FORMS).toEqual(["interview", "preview"]);
    for (const form of NON_MUSIC_FORMS) {
      expect(TRACK_FORMS).toContain(form);
      expect(SET_FORMS).not.toContain(form);
      expect(formParam(form, "sets")).toBeUndefined();
    }
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
