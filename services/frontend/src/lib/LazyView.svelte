<script>
  /**
   * Renders a view that lives in its own chunk (`lazyViews.js`, issue #114).
   *
   * While the chunk is on its way it shows the skeleton that fits the place -- track rows for a
   * page, nothing for an overlay or a sidebar, which would only flash -- and a failed fetch is a
   * section error with a retry pill (styleguide, Loading States). A chunk that is already in
   * renders on the first frame, so a revisit never shows a skeleton.
   *
   * @property {string} name - The view's name in the registry.
   * @property {ReturnType<import('./lazyViews.js').createLazyRegistry>} [registry] - Defaults
   *   to `lazyViews`.
   * @property {Record<string, any>} [props] - Passed through to the view.
   * @property {'rows'|'none'} [fallback] - What to show while loading.
   * @property {import('svelte').Snippet} [placeholder] - Shown while loading instead of
   *   `fallback`: the artist and album pages pass their seeded header (`EntityPageShell`), so
   *   the heading is on screen before the page's chunk is (issue #118).
   */
  import { untrack } from 'svelte';
  import { lazyViews } from './lazyViews.js';
  import SectionState from './loading/SectionState.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';

  const { name, registry = lazyViews, props = {}, fallback = 'rows', placeholder } = $props();

  let Component = $state(untrack(() => registry.peek(name)));
  let failed = $state(false);
  let attempt = $state(0);

  $effect(() => {
    const wanted = name;
    const from = registry;
    void attempt;
    const ready = from.peek(wanted);
    failed = false;
    if (ready) {
      Component = ready;
      return;
    }
    Component = null;
    let current = true;
    from.load(wanted).then(
      (loaded) => {
        if (current) Component = loaded;
      },
      (error) => {
        if (!current) return;
        console.error(`Could not load the "${wanted}" view`, error);
        failed = true;
      },
    );
    return () => {
      current = false;
    };
  });
</script>

{#if Component}
  <Component {...props} />
{:else if failed}
  <SectionState status="error" onretry={() => attempt++} />
{:else if placeholder}
  {@render placeholder()}
{:else if fallback === 'rows'}
  <div data-testid="lazy-view-loading">
    <SkeletonRows count={8} />
  </div>
{/if}
