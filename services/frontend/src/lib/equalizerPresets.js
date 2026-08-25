/**
 * Band layout and preset curves for the player equalizer.
 *
 * This module is pure data on purpose: the audio graph and the UI both read
 * from it, so there is exactly one place where the number of bands, their
 * frequencies and their limits are decided.
 */

/** Centre frequencies, one per band, roughly an octave apart. */
export const EQ_FREQUENCIES = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];

/**
 * Filter width. At Q = 1.41 each peaking filter covers about one octave, so
 * neighbouring bands overlap into a smooth curve instead of leaving audible
 * notches between them.
 */
export const EQ_Q = 1.41;

export const EQ_GAIN_MIN = -12;
export const EQ_GAIN_MAX = 12;
export const EQ_GAIN_STEP = 0.5;

/**
 * Preset curves, in the same band order as EQ_FREQUENCIES.
 *
 * Presets that lift a band hard carry a negative preamp: ten filters summing
 * into the same output clips well before the individual gains look extreme.
 */
export const EQ_PRESETS = {
  flat: { gains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], preamp: 0 },
  rock: { gains: [5, 4, 3, 1, -1, -1, 1, 3, 4, 4], preamp: -2 },
  pop: { gains: [-1, 0, 1, 3, 4, 3, 1, 0, -1, -2], preamp: -1 },
  jazz: { gains: [3, 2, 1, 2, -1, -1, 0, 1, 2, 3], preamp: -1 },
  classical: { gains: [3, 2, 0, 0, 0, 0, -1, -1, 2, 3], preamp: -1 },
  bassBoost: { gains: [7, 6, 5, 2, 0, 0, 0, 0, 0, 0], preamp: -3 },
  vocal: { gains: [-3, -3, -2, 0, 3, 4, 4, 3, 1, 0], preamp: -2 },
};

/** Preset keys in the order the picker shows them. */
export const EQ_PRESET_NAMES = Object.keys(EQ_PRESETS);

/**
 * The pseudo-preset the picker falls back to once the user drags a slider.
 * It has no curve of its own -- it only means "these gains match no preset".
 */
export const CUSTOM_PRESET = 'custom';
