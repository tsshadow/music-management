import { EQ_FREQUENCIES, EQ_Q } from "./equalizerPresets.js";

/**
 * The player's equalizer, as a plain module rather than a Svelte store: the
 * awkward parts here are all browser lifecycle, and keeping them out of a
 * component is what makes them testable.
 *
 * Two Web Audio facts shape everything below.
 *
 * An AudioContext may not be created before a user gesture, so the graph is
 * built lazily -- the first time the user switches the equalizer on. Listeners
 * who never open the panel never pay for one.
 *
 * createMediaElementSource() cannot be undone. Once it has run, all audio for
 * that element flows through this graph until the page is gone. Switching the
 * equalizer off therefore flattens every band to 0 dB, which is transparent,
 * instead of tearing the graph down and risking a silent player.
 */

let context = null;
let sourceNode = null;
let preampNode = null;
let filterNodes = [];

let attached = false;
let available = true;
let enabled = false;
let bandGains = EQ_FREQUENCIES.map(() => 0);
let preampDb = 0;

/** Test seam: lets the unit tests supply a stand-in for the missing jsdom API. */
let contextFactory = null;

function createContext() {
  if (contextFactory) return contextFactory();
  const Ctor = window.AudioContext || window.webkitAudioContext;
  return new Ctor();
}

function dbToLinear(db) {
  return 10 ** (db / 20);
}

/** True when this browser can host the equalizer at all. */
export function isSupported() {
  if (contextFactory) return true;
  if (typeof window === "undefined") return false;
  return Boolean(window.AudioContext || window.webkitAudioContext);
}

function applyGains() {
  if (!attached) return;
  filterNodes.forEach((filter, i) => {
    filter.gain.value = enabled ? bandGains[i] : 0;
  });
  preampNode.gain.value = enabled ? dbToLinear(preampDb) : 1;
}

/**
 * Builds the graph around `audioElement`. Safe to call repeatedly; only the
 * first call does anything.
 *
 * @param {HTMLAudioElement} audioElement
 * @returns {boolean} whether the equalizer is usable afterwards.
 */
export function attach(audioElement) {
  if (attached) return true;
  if (!available || !audioElement || !isSupported()) return false;

  try {
    context = createContext();
    sourceNode = context.createMediaElementSource(audioElement);

    preampNode = context.createGain();
    preampNode.gain.value = 1;

    filterNodes = EQ_FREQUENCIES.map((frequency) => {
      const filter = context.createBiquadFilter();
      filter.type = "peaking";
      filter.frequency.value = frequency;
      filter.Q.value = EQ_Q;
      filter.gain.value = 0;
      return filter;
    });

    sourceNode.connect(preampNode);
    let tail = preampNode;
    for (const filter of filterNodes) {
      tail.connect(filter);
      tail = filter;
    }
    tail.connect(context.destination);

    attached = true;
    applyGains();
    return true;
  } catch (e) {
    // A failed graph must never cost the user their audio: fall back to the
    // untouched element and stay out of the way for the rest of the session.
    console.error("Equalizer unavailable, continuing without it", e);
    available = false;
    context = null;
    sourceNode = null;
    preampNode = null;
    filterNodes = [];
    return false;
  }
}

/**
 * Switches the curve in or out. Off means every band at 0 dB and unity
 * preamp, which is transparent; the graph itself stays where it is.
 *
 * @param {boolean} value
 */
export function setEnabled(value) {
  enabled = Boolean(value);
  applyGains();
}

/**
 * @param {number} index - Band index into EQ_FREQUENCIES.
 * @param {number} gainDb
 */
export function setBand(index, gainDb) {
  if (index < 0 || index >= bandGains.length) return;
  bandGains[index] = gainDb;
  applyGains();
}

/**
 * Applies a whole curve at once, which is what choosing a preset does.
 *
 * @param {number[]} gains
 */
export function setGains(gains) {
  bandGains = EQ_FREQUENCIES.map((_, i) => gains[i] ?? 0);
  applyGains();
}

/** @param {number} gainDb */
export function setPreamp(gainDb) {
  preampDb = gainDb;
  applyGains();
}

/**
 * Browsers suspend contexts on backgrounded tabs and audio-device changes, and
 * a suspended context passes no sound. Called on every play.
 */
export function resume() {
  if (context && context.state === "suspended") {
    context.resume();
  }
}

/** @param {(() => object) | null} factory */
export function __setContextFactoryForTests(factory) {
  contextFactory = factory;
}

export function __resetForTests() {
  context = null;
  sourceNode = null;
  preampNode = null;
  filterNodes = [];
  attached = false;
  available = true;
  enabled = false;
  bandGains = EQ_FREQUENCIES.map(() => 0);
  preampDb = 0;
  contextFactory = null;
}
