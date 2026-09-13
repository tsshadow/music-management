import { describe, it, expect } from "vitest";
import { createCarModeSession, CarModeIntent } from "../../src/lib/carMode.js";

/**
 * The web port of `car/CarModeSession.kt`. Same cases as `CarModeSessionTest.kt`, minus the
 * `shouldRaise`/`isPlaying` branch: there is no notification here to raise, so `onPresenceChanged`
 * takes only the presence flag.
 */
describe("car mode session", () => {
  it("arriving in the car offers the screen", () => {
    const session = createCarModeSession();

    expect(session.onPresenceChanged(true)).toBe(CarModeIntent.OFFER);
  });

  it("leaving the car closes the screen", () => {
    const session = createCarModeSession();
    session.onPresenceChanged(true);

    expect(session.onPresenceChanged(false)).toBe(CarModeIntent.CLOSE);
  });

  it("a repeated presence signal offers nothing twice", () => {
    const session = createCarModeSession();
    session.onPresenceChanged(true);

    expect(session.onPresenceChanged(true)).toBe(CarModeIntent.NOTHING);
  });

  it("a dismissal stops the screen being offered again on this trip", () => {
    const session = createCarModeSession();
    session.onPresenceChanged(true);
    session.onDismissed();

    expect(session.onPresenceChanged(true)).toBe(CarModeIntent.NOTHING);
  });

  it("the next trip offers again", () => {
    const session = createCarModeSession();
    session.onPresenceChanged(true);
    session.onDismissed();
    session.onPresenceChanged(false);

    expect(session.onPresenceChanged(true)).toBe(CarModeIntent.OFFER);
  });

  it("leaving after a dismissal still closes", () => {
    const session = createCarModeSession();
    session.onPresenceChanged(true);
    session.onDismissed();

    expect(session.onPresenceChanged(false)).toBe(CarModeIntent.CLOSE);
  });

  it("leaving when never present does nothing", () => {
    const session = createCarModeSession();

    expect(session.onPresenceChanged(false)).toBe(CarModeIntent.NOTHING);
  });
});
