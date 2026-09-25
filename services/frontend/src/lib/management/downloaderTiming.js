/**
 * Helpers for the downloader Timing tab.
 *
 * The knobs are plain seconds and counts; these turn them into something a human
 * can read, and work out what actually has to be sent back to the API.
 */

import { get } from "svelte/store";
import { t } from "../i18n/index.js";

const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

/** The translation of one downloader key, looked up in the active locale at call time. */
function tr(key, vars) {
  return get(t)(`management.downloaders.${key}`, vars);
}

/** Render a number of seconds as a short duration in the active locale. */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "—";
  const total = Number(seconds);
  if (total === 0) return tr("duration.off");
  if (total < MINUTE) return tr("duration.seconds", { count: total });
  if (total < HOUR) return tr("duration.minutes", { count: Math.round(total / MINUTE) });
  if (total < DAY) {
    const hours = Math.floor(total / HOUR);
    const minutes = Math.round((total % HOUR) / MINUTE);
    const hoursText = tr("duration.hours", { count: hours });
    return minutes ? `${hoursText} ${tr("duration.minutes", { count: minutes })}` : hoursText;
  }
  const days = Math.floor(total / DAY);
  const hours = Math.round((total % DAY) / HOUR);
  const daysText = tr("duration.days", { count: days });
  return hours ? `${daysText} ${tr("duration.hours", { count: hours })}` : daysText;
}

/**
 * What a person has to do about a pause that waiting does not fix, keyed by the
 * `block_reason` the rate-state endpoint reports (bug report 076). The text
 * itself lives in the locale files under `management.downloaders.blockReason`.
 */
const BLOCK_REASONS = ["bot_check", "cookies_missing"];

/**
 * Summarise how hard a downloader is currently holding back.
 *
 * Returns a tone the UI can colour on: `ok` at full speed, `slowed` while the
 * multiplier is up, `parked` while a cooldown is running. A pause with a
 * `block_reason` also carries `advice`: the step that lifts it.
 */
export function describeBackoff(state) {
  if (!state) return { tone: "unknown", label: tr("backoff.unknown") };
  const multiplier = Number(state.multiplier || 1);
  const remaining = Number(state.cooldown_remaining || 0);
  const advice = BLOCK_REASONS.includes(state.block_reason)
    ? tr(`blockReason.${state.block_reason}`)
    : undefined;
  if (remaining > 0 && advice) {
    return {
      tone: "parked",
      label: tr("backoff.parked", { duration: formatDuration(remaining) }),
      advice,
    };
  }
  if (remaining > 0) {
    return {
      tone: "parked",
      label: tr("backoff.parkedSlowed", { duration: formatDuration(remaining), multiplier }),
    };
  }
  if (multiplier > 1) {
    return { tone: "slowed", label: tr("backoff.slowed", { multiplier }) };
  }
  return { tone: "ok", label: tr("backoff.normal") };
}

/**
 * The knobs whose edited value differs from what is currently stored.
 *
 * Blank and non-numeric input is dropped rather than sent, so a half-typed field
 * cannot wipe a setting.
 */
export function changedValues(fields, edited) {
  const updates = {};
  for (const field of fields) {
    const raw = edited[field.key];
    if (raw === "" || raw === null || raw === undefined) continue;
    const value = Number(raw);
    if (Number.isNaN(value)) continue;
    if (value !== Number(field.value)) updates[field.key] = value;
  }
  return updates;
}
