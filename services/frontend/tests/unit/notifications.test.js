import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  notifications,
  notify,
  dismiss,
  dismissAll,
  pauseTimers,
  resumeTimers,
  LIFETIMES,
  MAX_VISIBLE,
} from "../../src/lib/notifications.js";

describe("notifications", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    dismissAll();
  });

  afterEach(() => {
    dismissAll();
    vi.useRealTimers();
  });

  it("adds a notification with its type and message", () => {
    notify.error("Beoordeling mislukt");

    expect(get(notifications)).toMatchObject([
      { type: "error", message: "Beoordeling mislukt", detail: null, count: 1 },
    ]);
  });

  it("keeps the detail line when one is given", () => {
    notify.warning("Scrobble mislukt", { detail: "HTTP 503" });

    expect(get(notifications)[0].detail).toBe("HTTP 503");
  });

  it("hands back an id that dismisses that notification", () => {
    const id = notify.info("Bezig");
    notify.info("Iets anders");

    dismiss(id);

    expect(get(notifications).map((n) => n.message)).toEqual(["Iets anders"]);
  });

  it("an error never expires on its own", () => {
    notify.error("Beoordeling mislukt");

    vi.advanceTimersByTime(10 * 60 * 1000);

    expect(get(notifications)).toHaveLength(1);
  });

  it.each([
    ["warning", LIFETIMES.warning],
    ["info", LIFETIMES.info],
    ["success", LIFETIMES.success],
  ])("a %s clears itself after its lifetime", (type, lifetime) => {
    notify[type]("Weg hiermee");

    vi.advanceTimersByTime(lifetime - 1);
    expect(get(notifications)).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(get(notifications)).toHaveLength(0);
  });

  it("counts a repeat instead of stacking it", () => {
    notify.error("Beoordeling mislukt");
    notify.error("Beoordeling mislukt");
    notify.error("Beoordeling mislukt");

    expect(get(notifications)).toHaveLength(1);
    expect(get(notifications)[0].count).toBe(3);
  });

  it("does not merge the same message under a different type", () => {
    notify.error("Hetzelfde");
    notify.info("Hetzelfde");

    expect(get(notifications)).toHaveLength(2);
  });

  it("a repeat restarts the timer", () => {
    notify.info("Nogmaals");

    vi.advanceTimersByTime(LIFETIMES.info - 100);
    notify.info("Nogmaals");
    vi.advanceTimersByTime(200);

    expect(get(notifications)).toHaveLength(1);
  });

  it("drops the oldest expiring notification when full", () => {
    notify.info("een");
    notify.error("twee");
    for (const message of ["drie", "vier", "vijf", "zes"]) notify.error(message);

    const messages = get(notifications).map((n) => n.message);
    expect(messages).toHaveLength(MAX_VISIBLE);
    expect(messages).not.toContain("een");
    expect(messages).toContain("zes");
  });

  it("drops the oldest error when every slot holds one", () => {
    for (const message of ["een", "twee", "drie", "vier", "vijf"]) notify.error(message);

    notify.error("zes");

    const messages = get(notifications).map((n) => n.message);
    expect(messages).toEqual(["twee", "drie", "vier", "vijf", "zes"]);
  });

  it("holds the timers while the pointer rests on the stack", () => {
    notify.info("Blijf staan");

    pauseTimers();
    vi.advanceTimersByTime(LIFETIMES.info * 3);
    expect(get(notifications)).toHaveLength(1);

    resumeTimers();
    vi.advanceTimersByTime(LIFETIMES.info);
    expect(get(notifications)).toHaveLength(0);
  });

  it("dismissAll empties the stack", () => {
    notify.error("een");
    notify.error("twee");

    dismissAll();

    expect(get(notifications)).toEqual([]);
  });
});
