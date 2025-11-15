<script lang="ts">
  export let title: string;
  export let description: string;
  export let align: 'center' | 'start' = 'center';
</script>

<header class={`ui-hero ui-hero--${align}`}>
  <div class="ui-hero__backdrop" aria-hidden="true"></div>
  <div class="ui-hero__content">
    <slot name="eyebrow" />
    <h1>{title}</h1>
    <p>{description}</p>
    <slot />
  </div>
</header>

<style>
  .ui-hero {
    position: relative;
    padding: var(--space-3xl) var(--space-md) var(--space-2xl);
    display: flex;
    justify-content: center;
    align-items: center;
    color: var(--color-text-primary);
    overflow: hidden;
  }

  .ui-hero--start {
    justify-content: flex-start;
  }

  .ui-hero__backdrop {
    position: absolute;
    inset: 0;
    background: var(--gradient-hero);
    filter: blur(60px);
    opacity: 0.65;
    z-index: 0;
  }

  .ui-hero__content {
    position: relative;
    z-index: 1;
    text-align: center;
    max-width: 720px;
  }

  .ui-hero--start .ui-hero__content {
    text-align: left;
    margin-left: auto;
    margin-right: auto;
  }

  h1 {
    margin: 0 0 var(--space-sm);
    font-size: clamp(2.5rem, 4vw, 4rem);
    line-height: var(--line-height-tight);
  }

  p {
    margin: 0;
    font-size: var(--font-size-lg);
    line-height: var(--line-height-snug);
    color: var(--color-text-muted);
  }

  :global(.ui-hero [slot='eyebrow']) {
    display: inline-block;
    margin-bottom: var(--space-xs);
    text-transform: uppercase;
    letter-spacing: 0.35em;
    font-size: var(--font-size-xs);
    color: var(--color-text-soft);
  }
</style>
