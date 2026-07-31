/**
 * Helpers for the downloader Timing tab.
 *
 * The knobs are plain seconds and counts; these turn them into something a human
 * can read, and work out what actually has to be sent back to the API.
 */

const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;

/** Render a number of seconds as a short Dutch duration. */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '—';
  const total = Number(seconds);
  if (total === 0) return 'uit';
  if (total < MINUTE) return `${total} sec`;
  if (total < HOUR) return `${Math.round(total / MINUTE)} min`;
  if (total < DAY) {
    const hours = Math.floor(total / HOUR);
    const minutes = Math.round((total % HOUR) / MINUTE);
    return minutes ? `${hours} uur ${minutes} min` : `${hours} uur`;
  }
  const days = Math.floor(total / DAY);
  const hours = Math.round((total % DAY) / HOUR);
  return hours ? `${days} dag ${hours} uur` : `${days} dag${days > 1 ? 'en' : ''}`;
}

/**
 * Summarise how hard a downloader is currently holding back.
 *
 * Returns a tone the UI can colour on: `ok` at full speed, `slowed` while the
 * multiplier is up, `parked` while a cooldown is running.
 */
export function describeBackoff(state) {
  if (!state) return { tone: 'unknown', label: 'Onbekend' };
  const multiplier = Number(state.multiplier || 1);
  const remaining = Number(state.cooldown_remaining || 0);
  if (remaining > 0) {
    return {
      tone: 'parked',
      label: `Gepauzeerd, nog ${formatDuration(remaining)} (${multiplier}x vertraagd)`,
    };
  }
  if (multiplier > 1) {
    return { tone: 'slowed', label: `${multiplier}x vertraagd, herstelt na schone rondes` };
  }
  return { tone: 'ok', label: 'Normaal tempo' };
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
    if (raw === '' || raw === null || raw === undefined) continue;
    const value = Number(raw);
    if (Number.isNaN(value)) continue;
    if (value !== Number(field.value)) updates[field.key] = value;
  }
  return updates;
}
