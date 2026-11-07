/**
 * How the Radio page reaches the player.
 *
 * `Player.svelte` owns the audio element and the service commands, and stays mounted while the
 * page changes. The calls are plain functions and not a store with an effect, because a browser
 * lets playback start only in the same task as the tap.
 */

let commands = null;

/**
 * Makes the player's radio functions available to the page.
 *
 * @param {{startRadio: Function, startStation: Function, stop: Function}} handlers
 * @returns {() => void} Removes them again, for `onMount`.
 */
export function registerRadioCommands(handlers) {
  commands = handlers;
  return () => {
    if (commands === handlers) commands = null;
  };
}

/**
 * Starts one MuMa Radio channel.
 *
 * @param {{slug: string}} channel
 */
export function tuneChannel(channel) {
  return commands?.startRadio(channel);
}

/**
 * Starts one live station.
 *
 * @param {{slug: string, name: string, stream_url: string}} station
 */
export function tuneStation(station) {
  return commands?.startStation(station);
}

/** Stops the station or channel that plays. */
export function leaveRadio() {
  return commands?.stop();
}
