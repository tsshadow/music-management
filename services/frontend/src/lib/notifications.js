import { writable, get } from "svelte/store";

/**
 * How long a notification of each type stays on screen, in milliseconds.
 *
 * `error` is deliberately `null`: a failure the user did not see is a failure
 * they will report as "it just did nothing", so it waits for them to dismiss
 * it (or for the page to reload) rather than expiring while they look away.
 */
export const LIFETIMES = {
  error: null,
  warning: 8000,
  info: 5000,
  success: 4000,
};

/**
 * How many notifications are shown at once. Beyond this the corner stops
 * being readable, which defeats the point of the feature.
 */
export const MAX_VISIBLE = 5;

/** @typedef {'error'|'warning'|'info'|'success'} NotificationType */

/**
 * The notifications currently on screen, oldest first.
 *
 * @type {import('svelte/store').Writable<Array<{id: number, type: NotificationType, message: string, detail: string|null, action: {label: string, onClick: Function}|null, count: number}>>}
 */
export const notifications = writable([]);

let nextId = 1;

// The live countdown per notification id. `remaining` is what is left of the
// lifetime, kept so hovering can stop the clock and resume it rather than
// restart it.
const timers = new Map();
let paused = false;

function clearTimer(id) {
  const timer = timers.get(id);
  if (!timer) return;
  clearTimeout(timer.handle);
  timers.delete(id);
}

function startTimer(id, remaining) {
  clearTimer(id);
  if (remaining === null) return;
  const handle = paused ? null : setTimeout(() => dismiss(id), remaining);
  timers.set(id, { handle, remaining, startedAt: Date.now() });
}

/**
 * Removes one notification.
 *
 * @param {number} id - The id returned by a `notify.*` call.
 */
export function dismiss(id) {
  clearTimer(id);
  notifications.update((list) => list.filter((item) => item.id !== id));
}

/**
 * A snapshot of the live countdowns.
 *
 * Every loop below deletes and re-adds the entries it walks, and a live map
 * iterator hands a re-added key back a second time -- which, in
 * `resumeTimers`, never terminates. Taking a copy first is what makes those
 * loops safe, so it is deliberate rather than the redundant spread it looks
 * like.
 *
 * @returns {Array<[number, {handle: any, remaining: number, startedAt: number}]>}
 */
function timerSnapshot() {
  return Array.from(timers.entries());
}

/** Removes every notification. */
export function dismissAll() {
  for (const [id] of timerSnapshot()) clearTimer(id);
  notifications.set([]);
}

/**
 * Freezes every running countdown, so a notification cannot expire while the
 * user is reading it or reaching for its close button.
 */
export function pauseTimers() {
  if (paused) return;
  paused = true;
  for (const [id, timer] of timerSnapshot()) {
    if (timer.handle === null) continue;
    clearTimeout(timer.handle);
    const elapsed = Date.now() - timer.startedAt;
    timers.set(id, {
      handle: null,
      remaining: Math.max(0, timer.remaining - elapsed),
      startedAt: Date.now(),
    });
  }
}

/** Resumes the countdowns `pauseTimers` froze, from where each one stopped. */
export function resumeTimers() {
  if (!paused) return;
  paused = false;
  for (const [id, timer] of timerSnapshot()) startTimer(id, timer.remaining);
}

/**
 * Makes room for one more notification once the stack is full.
 *
 * Something that expires on its own is dropped before an error is, because an
 * error is the one the user still has to act on. When there is nothing but
 * errors, the oldest one goes -- silently swallowing the newest failure would
 * hide exactly the thing that just happened.
 *
 * @param {Array} list
 * @returns {Array} The list with room for one more.
 */
function evictOne(list) {
  if (list.length < MAX_VISIBLE) return list;
  const victim = list.find((item) => LIFETIMES[item.type] !== null) ?? list[0];
  clearTimer(victim.id);
  return list.filter((item) => item !== victim);
}

/**
 * Adds a notification, or counts it against an identical one already on
 * screen.
 *
 * An identical notification with an `action` is never merged into an
 * existing one -- set resume is the one caller that passes one, and it is
 * always for a different set, so re-counting it under someone else's
 * "opnieuw" button would fire the wrong track's restart.
 *
 * @param {NotificationType} type
 * @param {string} message - Already translated; this module holds no i18n.
 * @param {{detail?: string, action?: {label: string, onClick: Function}}} [options]
 * @returns {number} The notification's id, for an early `dismiss`.
 */
function add(type, message, options = {}) {
  const existing = !options.action
    ? get(notifications).find((item) => item.type === type && item.message === message)
    : null;
  if (existing) {
    notifications.update((list) =>
      list.map((item) => (item.id === existing.id ? { ...item, count: item.count + 1 } : item)),
    );
    startTimer(existing.id, LIFETIMES[type]);
    return existing.id;
  }

  const id = nextId++;
  notifications.update((list) => [
    ...evictOne(list),
    { id, type, message, detail: options.detail ?? null, action: options.action ?? null, count: 1 },
  ]);
  startTimer(id, LIFETIMES[type]);
  return id;
}

/**
 * Reports something to the user in the notification stack.
 *
 * Use `error` for an action that failed and left nothing behind, `warning`
 * for one that failed without stopping what the user was doing, `info` for
 * context, and `success` for a confirmation that is not otherwise visible on
 * screen.
 */
export const notify = {
  error: (message, options) => add("error", message, options),
  warning: (message, options) => add("warning", message, options),
  info: (message, options) => add("info", message, options),
  success: (message, options) => add("success", message, options),
};
