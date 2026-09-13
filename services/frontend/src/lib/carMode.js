/**
 * One trip's memory of whether the web car screen should open itself.
 *
 * Ported from the Kotlin `car/CarModeSession.kt`, which the legacy screen and its notification
 * still use. The web UI has no notification step -- `platform.system.carConnected` reaches an
 * already-open app directly -- so `OFFER` here means "navigate to the car screen" rather than
 * "post a notification", and the Kotlin `shouldRaise`/`isPlaying` distinction (whether a
 * notification may use a full-screen intent) has nothing to answer to on this side and is left
 * out. Presence and dismissal are the two things that still mean the same thing in both places:
 *
 * - Pressing close has to mean something for longer than an instant, or a car that re-reports its
 *   connection (a Bluetooth reconnect blip, `refreshManual()` on the native side) reopens the
 *   screen right under the driver's thumb.
 * - It has to stop meaning something once the trip ends, or closing the screen on Monday would
 *   silence the feature forever.
 *
 * This is a second, independent state machine from the Kotlin `CarModeSession` that gates the
 * native notification -- not a client of it. Both derive from the same underlying presence
 * signal and so stay in lock-step in spirit, but there is no call from here back into Kotlin:
 * dismissing the in-app screen must not be confused with dismissing a notification the app
 * receiving the same `connected` value never has to show in the first place.
 */

/** What a presence change should do to the web car screen. */
export const CarModeIntent = Object.freeze({
  OFFER: "offer",
  CLOSE: "close",
  NOTHING: "nothing",
});

/**
 * @returns {{onPresenceChanged: function(boolean): string, onDismissed: function(): void}}
 */
export function createCarModeSession() {
  let present = false;
  let dismissed = false;

  return {
    /**
     * @param {boolean} inCar
     * @returns {string} One of {@link CarModeIntent}.
     */
    onPresenceChanged(inCar) {
      if (inCar === present) return CarModeIntent.NOTHING;
      present = inCar;

      if (!inCar) {
        dismissed = false;
        return CarModeIntent.CLOSE;
      }

      if (dismissed) return CarModeIntent.NOTHING;
      return CarModeIntent.OFFER;
    },

    /** Stops the screen being offered again for the rest of this trip. */
    onDismissed() {
      dismissed = true;
    },
  };
}
