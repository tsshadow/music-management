/**
 * The setup tour: a short, curated walk through the settings that decide how
 * MuMa fits the listener, shown once on a first run and again -- only the new
 * steps -- after an update that brought a setting worth deciding on.
 *
 * The list is the whole design. Each step names the settings it lets the
 * listener decide; `SetupWizard.svelte` renders the matching controls, bound to
 * the very same stores the settings pages write, so the tour can never disagree
 * with the settings screen. The account remembers which step ids it has been
 * through (`setupStepsSeen` in `store.js`); a step whose id is not in that list
 * is pending, which is what makes adding a step for a new setting a one-line
 * change here and an automatic one-time prompt for everyone.
 *
 * Ids are permanent: renaming one would re-show the step to every account.
 */

/**
 * The tour, in order. `native` marks a step that only exists inside the phone
 * shell (there is nothing to decide about downloads in a browser tab).
 *
 * @type {Array<{id: string, native?: boolean}>}
 */
export const SETUP_STEPS = [
  { id: "language" },
  { id: "mode" },
  { id: "home" },
  { id: "display" },
  { id: "downloads", native: true },
  { id: "guide" },
];

/**
 * The steps this listener still has to be walked through, in tour order.
 *
 * @param {string[]} seen - Step ids the account has been through.
 * @param {{storage?: {supported?: boolean}}} [platform] - The shell's capabilities.
 * @returns {Array<{id: string, native?: boolean}>}
 */
export function pendingSteps(seen, platform) {
  const done = new Set(Array.isArray(seen) ? seen : []);
  const native = platform?.storage?.supported === true;
  return SETUP_STEPS.filter((step) => (!step.native || native) && !done.has(step.id));
}

/**
 * Every step this platform offers, whether seen or not -- what "run the tour
 * again" from the manual walks through.
 *
 * @param {{storage?: {supported?: boolean}}} [platform]
 * @returns {Array<{id: string, native?: boolean}>}
 */
export function allSteps(platform) {
  return pendingSteps([], platform);
}

/**
 * Whether a run is an update run -- the account has been through the tour
 * before and only new steps are pending -- as opposed to a first run. The
 * wizard badges the steps "new" in the first case and says "welcome" in the
 * second.
 *
 * @param {string[]} seen
 * @returns {boolean}
 */
export function isUpdateRun(seen) {
  return Array.isArray(seen) && seen.length > 0;
}

/**
 * The ids to record once a run finishes: everything already seen plus the
 * steps just walked through, deduplicated, so a skipped run is recorded the
 * same as a completed one and the tour never nags.
 *
 * @param {string[]} seen
 * @param {Array<{id: string}>} steps
 * @returns {string[]}
 */
export function markSeen(seen, steps) {
  return [...new Set([...(Array.isArray(seen) ? seen : []), ...steps.map((step) => step.id)])];
}
