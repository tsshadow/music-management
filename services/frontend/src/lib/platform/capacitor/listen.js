/**
 * One subscription helper for all five plugins.
 *
 * Capacitor's `addListener` returns a *promise* of a handle, while the platform
 * contract in `../index.js` promises a plain unsubscribe function that is safe
 * to call at once. Bridging the two is the whole of this file: the promise is
 * kept, the returned function removes the handle whenever it arrives, and a
 * caller that unsubscribes before the bridge answered still ends up with the
 * listener removed rather than with a leak nobody can see.
 *
 * A failed subscription is logged and swallowed. The alternative -- rejecting
 * -- would be an unhandled rejection in a component's `onMount`, and a screen
 * that fails to render because an event it does not need did not arrive is a
 * worse outcome than a silent event.
 *
 * @param {{addListener: function(string, Function): (Promise<{remove: Function}>|{remove: Function})}} plugin
 * @param {string} event - The event name the Kotlin plugin emits.
 * @param {function(object): void} handler
 * @returns {function(): void} Unsubscribes.
 */
export function listen(plugin, event, handler) {
  // Called straight away rather than from a `.then`: the bridge registers the
  // handler the moment it is handed over, and deferring that by a microtask
  // would drop an event the shell sent while the app was still starting -- a
  // deep link from a launcher shortcut arrives exactly then.
  let pending;
  try {
    pending = Promise.resolve(plugin.addListener(event, handler));
  } catch (error) {
    pending = Promise.reject(error);
  }
  pending = pending.catch((error) => {
    console.error("Could not subscribe to a platform event", event, error);
    return null;
  });

  return () => {
    pending
      .then((handle) => handle?.remove?.())
      .catch((error) => console.error("Could not unsubscribe from", event, error));
  };
}

/**
 * Calls a plugin method and swallows a rejection into a console warning.
 *
 * Used for the fire-and-forget half of the player contract -- `pause`, `seek`,
 * `setVolume` -- which the browser implementation performs synchronously and
 * every caller therefore treats as returning nothing. Without this each of them
 * would be an unhandled promise rejection the first time the service is not
 * bound yet.
 *
 * @param {string} what - What was attempted, for the log line.
 * @param {Promise<any>|any} call - The plugin call, already made.
 */
export function fireAndForget(what, call) {
  Promise.resolve(call).catch((error) => console.warn("Platform call failed", what, error));
}
