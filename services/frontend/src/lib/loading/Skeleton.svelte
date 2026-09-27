<script>
  /**
   * One skeleton block: the style guide's loading placeholder (`muma-skeleton`, the 700ms
   * `skeleton-pulse`). Its size and shape come from `class`, so it can stand in for a title, a
   * cover or a portrait with the same geometry as the real thing and nothing shifts when that
   * arrives. Hidden from assistive tech; the surrounding section says "loading" once.
   */
  const { class: className = '' } = $props();
</script>

<div class="bg-muma-skeleton skeleton-pulse rounded {className}" aria-hidden="true" data-testid="skeleton"></div>
