import { medianClockOffset, targetPosition, correction } from "./radioSync.js";

/**
 * Drives an <audio> element from a server-owned radio timeline.
 *
 * The controller never pushes anything: it reads `/api/radio/{slug}/state`,
 * works out where playback should be from the entry's absolute `started_at`,
 * and keeps the local element on that point. Because LMS only honours
 * `timeOffset` while transcoding, joining mid-track means requesting a fresh
 * stream URL rather than seeking, so `srcOffset` tracks where the current
 * source begins.
 *
 * `audio` may be null: on the native shell the platform service streams the channel and corrects
 * its own drift against the server's timeline itself
 * (`RadioPlaybackController.kt`/`RadioSync.kt`, reusing what Android Auto's radio support already
 * has), so a second instance of this controller is only kept around there for `getEntry()` --
 * `Player.svelte` still wants somewhere to read the now-playing metadata from. Every place that
 * would touch the element becomes a no-op instead of a crash.
 *
 * @param {Object} options
 * @param {HTMLAudioElement|null} options.audio
 * @param {string} options.apiBase - e.g. "/muma"
 * @param {string} options.apiKey
 * @param {function(string, number): string} options.streamUrlFor
 * @param {typeof fetch} [options.fetchImpl]
 * @param {function(): number} [options.now] - local clock in ms.
 * @param {number} [options.sampleCount] - clock-offset samples to take.
 */
export function createRadioController({
  audio,
  apiBase,
  apiKey,
  streamUrlFor,
  fetchImpl = fetch,
  now = () => Date.now(),
  sampleCount = 5,
}) {
  let slug = null;
  let clockOffsetMs = 0;
  let entry = null;
  let srcOffset = 0;

  const headers = { "X-API-Key": apiKey };

  function serverNowMs() {
    return now() + clockOffsetMs;
  }

  function localPosition() {
    return srcOffset + (audio?.currentTime || 0);
  }

  async function measureClockOffset() {
    const samples = [];
    for (let i = 0; i < sampleCount; i++) {
      const t0 = now();
      const response = await fetchImpl(`${apiBase}/api/radio/time`, { headers });
      const t1 = now();
      const body = await response.json();
      samples.push({ t0, t1, serverTime: body.server_time * 1000 });
    }
    clockOffsetMs = medianClockOffset(samples);
  }

  function loadEntryAt(nextEntry, position) {
    const offset = Math.max(0, Math.floor(position));
    srcOffset = offset;
    // Display-only mode: see the `audio` note on `createRadioController`.
    if (!audio) return;
    audio.playbackRate = 1;
    audio.src = streamUrlFor(nextEntry.track_id, offset);
    audio.play().catch(() => {});
  }

  async function refresh() {
    if (!slug) return;
    const asked = slug;
    const response = await fetchImpl(`${apiBase}/api/radio/${asked}/state`, { headers });
    const state = await response.json();
    // Stopped, retired or switched while the request was out: this answer belongs to a channel
    // nobody is listening to any more, and loading it would start a second stream.
    if (slug !== asked) return;

    // Deliberately NOT re-anchoring the clock from this response: its latency is
    // unknown (it hits the database), so a single sample from it would be worse
    // than the median measured against the DB-free /time endpoint. Callers
    // re-run measureClockOffset() periodically instead.

    if (!state.current) {
      entry = null;
      return;
    }

    const changed =
      !entry ||
      entry.track_id !== state.current.track_id ||
      entry.started_at !== state.current.started_at;
    entry = state.current;
    if (changed) {
      loadEntryAt(entry, targetPosition({ startedAtMs: entry.started_at * 1000 }, serverNowMs()));
    }
  }

  function tick() {
    if (!slug || !entry) return;
    // Display-only mode: the platform service corrects its own drift; see the `audio` note above.
    if (!audio) return;
    const target = targetPosition({ startedAtMs: entry.started_at * 1000 }, serverNowMs());
    const result = correction(localPosition(), target);
    if (result.action === "seek") {
      loadEntryAt(entry, target);
    } else {
      audio.playbackRate = result.rate;
    }
  }

  async function start(channelSlug) {
    slug = channelSlug;
    await measureClockOffset();
    if (slug !== channelSlug) return;
    await refresh();
  }

  /**
   * Stops this controller from ever touching the element again, without pausing it -- a newer
   * controller has taken over the element (a channel switch) and is about to load its own stream.
   * A `start` or `refresh` still in flight finishes as a no-op.
   */
  function retire() {
    slug = null;
    entry = null;
  }

  function stop() {
    slug = null;
    entry = null;
    srcOffset = 0;
    if (!audio) return;
    audio.playbackRate = 1;
    audio.pause();
  }

  return { start, stop, retire, tick, refresh, measureClockOffset, getEntry: () => entry };
}
