import { describe, it, expect } from "vitest";
import {
  SECRET_SENTINEL,
  groupFields,
  coerceValue,
  changedUpdates,
  isSecretPlaceholder,
} from "../../src/lib/management/configFields";

const field = (over = {}) => ({
  key: "notify_topic",
  type: "string",
  group: "Notifications",
  description: "",
  default: "",
  secret: false,
  value: "",
  ...over,
});

describe("groupFields", () => {
  it("puts each field under its own group", () => {
    const grouped = groupFields([
      field({ key: "a", group: "Tagger" }),
      field({ key: "b", group: "Paths" }),
      field({ key: "c", group: "Tagger" }),
    ]);
    expect(grouped.map((g) => g.name)).toEqual(["Tagger", "Paths"]);
    expect(grouped[0].fields.map((f) => f.key)).toEqual(["a", "c"]);
  });

  it("keeps the order the backend sent, which is the order of the schema", () => {
    const grouped = groupFields([
      field({ key: "a", group: "Zebra" }),
      field({ key: "b", group: "Alpha" }),
    ]);
    expect(grouped.map((g) => g.name)).toEqual(["Zebra", "Alpha"]);
  });

  it("survives an empty schema rather than rendering nothing at all", () => {
    expect(groupFields([])).toEqual([]);
  });
});

describe("coerceValue", () => {
  it("reads a number field back as a number", () => {
    expect(coerceValue(field({ type: "integer" }), "50")).toBe(50);
  });

  it("leaves an empty number field as null rather than sending NaN", () => {
    expect(coerceValue(field({ type: "integer" }), "")).toBe(null);
  });

  it("refuses a number that is not one, so the backend never sees NaN", () => {
    expect(coerceValue(field({ type: "integer" }), "twelve")).toBe(null);
  });

  it("passes a boolean through", () => {
    expect(coerceValue(field({ type: "boolean" }), true)).toBe(true);
  });

  it("passes a string through untouched, spaces included", () => {
    // A path may legitimately end in a space; trimming here would corrupt it.
    expect(coerceValue(field(), " /mnt/music ")).toBe(" /mnt/music ");
  });
});

describe("isSecretPlaceholder", () => {
  it("recognises an untouched secret", () => {
    expect(isSecretPlaceholder(field({ secret: true }), SECRET_SENTINEL)).toBe(true);
  });

  it("does not treat a typed secret as untouched", () => {
    expect(isSecretPlaceholder(field({ secret: true }), "hunter2")).toBe(false);
  });

  it("does not apply to an ordinary field that happens to hold bullets", () => {
    expect(isSecretPlaceholder(field({ secret: false }), SECRET_SENTINEL)).toBe(false);
  });
});

describe("changedUpdates", () => {
  const fields = [
    field({ key: "notify_topic", value: "music-management" }),
    field({ key: "max_retag_files", type: "integer", group: "Tagger", value: 2000 }),
    field({ key: "db_pass", secret: true, value: SECRET_SENTINEL }),
  ];

  it("sends nothing when nothing was edited", () => {
    const draft = {
      notify_topic: "music-management",
      max_retag_files: 2000,
      db_pass: SECRET_SENTINEL,
    };
    expect(changedUpdates(fields, draft)).toEqual({});
  });

  it("sends only the field that changed", () => {
    const draft = { notify_topic: "alerts", max_retag_files: 2000, db_pass: SECRET_SENTINEL };
    expect(changedUpdates(fields, draft)).toEqual({ notify_topic: "alerts" });
  });

  it("never sends an untouched secret back", () => {
    // The backend ignores the sentinel too, but not sending it at all means a save
    // cannot depend on the two agreeing about what the mask means.
    const draft = { notify_topic: "alerts", max_retag_files: 2000, db_pass: SECRET_SENTINEL };
    expect(changedUpdates(fields, draft)).not.toHaveProperty("db_pass");
  });

  it("does send a secret the user actually typed", () => {
    const draft = { notify_topic: "music-management", max_retag_files: 2000, db_pass: "hunter2" };
    expect(changedUpdates(fields, draft)).toEqual({ db_pass: "hunter2" });
  });

  it("sends a cleared secret, because emptying one is a real intent", () => {
    const draft = { notify_topic: "music-management", max_retag_files: 2000, db_pass: "" };
    expect(changedUpdates(fields, draft)).toEqual({ db_pass: "" });
  });

  it('coerces a number typed as text before comparing, so 2000 is not "changed"', () => {
    const draft = {
      notify_topic: "music-management",
      max_retag_files: "2000",
      db_pass: SECRET_SENTINEL,
    };
    expect(changedUpdates(fields, draft)).toEqual({});
  });

  it("never sends a read-only field, which the backend would refuse", () => {
    const withReadOnly = [
      ...fields,
      field({ key: "db_host", group: "Database", read_only: true, value: "mariadb" }),
    ];
    const draft = {
      notify_topic: "music-management",
      max_retag_files: 2000,
      db_pass: SECRET_SENTINEL,
      db_host: "elsewhere",
    };
    expect(changedUpdates(withReadOnly, draft)).toEqual({});
  });

  it("sends a genuinely changed number as a number", () => {
    const draft = {
      notify_topic: "music-management",
      max_retag_files: "50",
      db_pass: SECRET_SENTINEL,
    };
    expect(changedUpdates(fields, draft)).toEqual({ max_retag_files: 50 });
  });
});
