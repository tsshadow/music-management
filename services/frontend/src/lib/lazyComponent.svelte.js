/**
 * A component from a lazy registry (`lazyViews.js`) as reactive state, for the places
 * `LazyView.svelte` cannot serve: a part rendered with `bind:` props, which a props object
 * cannot carry (`FilterBar`, `CollectionBar`, `CollectionGrid`; issue #118), and the full-screen
 * player, which stays mounted once loaded so its open/close animation keeps working (issue #119).
 *
 * `current` is the component once its chunk is in -- at once when it already was, which is the
 * case after the boot preload or the idle preload -- and `null` before. `load()` starts the fetch;
 * a failure is logged, `failed` turns true until the next `load()`, and the next `load()` (the
 * next visit, or a retry button) tries again.
 *
 * @param {ReturnType<import('./lazyViews.js').createLazyRegistry>} registry
 * @param {string} name
 * @returns {{readonly current: any, readonly failed: boolean, load: () => void}}
 */
export function lazyComponent(registry, name) {
  let component = $state(registry.peek(name));
  let failed = $state(false);
  let loading = false;
  return {
    get current() {
      return component;
    },
    get failed() {
      return failed;
    },
    load() {
      if (component || loading) return;
      loading = true;
      failed = false;
      registry.load(name).then(
        (loaded) => {
          loading = false;
          component = loaded;
        },
        (error) => {
          loading = false;
          failed = true;
          console.error("Could not load a lazy part:", name, error);
        },
      );
    },
  };
}
