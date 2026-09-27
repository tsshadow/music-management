/**
 * A component from a lazy registry (`lazyViews.js`) as reactive state, for the places
 * `LazyView.svelte` cannot serve: a part rendered with `bind:` props, which a props object
 * cannot carry (`FilterBar`, `CollectionBar`, `CollectionGrid`; issue #118).
 *
 * `current` is the component once its chunk is in -- at once when it already was, which is the
 * case after the boot preload or the idle preload -- and `null` before. `load()` starts the fetch;
 * a failure is logged and forgotten, so the next `load()` (the next visit) tries again.
 *
 * @param {ReturnType<import('./lazyViews.js').createLazyRegistry>} registry
 * @param {string} name
 * @returns {{readonly current: any, load: () => void}}
 */
export function lazyComponent(registry, name) {
  let component = $state(registry.peek(name));
  let loading = false;
  return {
    get current() {
      return component;
    },
    load() {
      if (component || loading) return;
      loading = true;
      registry.load(name).then(
        (loaded) => {
          loading = false;
          component = loaded;
        },
        (error) => {
          loading = false;
          console.error(`Could not load the "${name}" part`, error);
        },
      );
    },
  };
}
