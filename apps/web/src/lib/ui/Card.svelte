<script lang="ts">
  export type CardPadding = 'sm' | 'md' | 'lg' | 'xl';
  export type CardVariant = 'surface' | 'translucent';

  export let element: keyof HTMLElementTagNameMap = 'div';
  export let padding: CardPadding = 'lg';
  export let variant: CardVariant = 'translucent';
  export let interactive = false;
  export let className = '';
</script>

<svelte:element
  this={element}
  class={`ui-card ui-card--${variant} ui-card--pad-${padding} ${interactive ? 'ui-card--interactive' : ''} ${className}`.trim()}
  {...$$restProps}
>
  <slot />
</svelte:element>

<style>
  .ui-card {
    background: var(--color-surface-1);
    border-radius: var(--radius-lg);
    border: 1px solid var(--color-border-subtle);
    box-shadow: var(--shadow-lg);
    color: inherit;
    display: block;
    transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease;
  }

  .ui-card--surface {
    background: var(--color-surface-overlay);
    box-shadow: var(--shadow-md);
  }

  .ui-card--translucent {
    background: var(--color-surface-1);
    backdrop-filter: blur(20px);
  }

  .ui-card--pad-sm {
    padding: var(--space-sm);
  }

  .ui-card--pad-md {
    padding: var(--space-md);
  }

  .ui-card--pad-lg {
    padding: var(--space-lg);
  }

  .ui-card--pad-xl {
    padding: var(--space-xl) var(--space-2xl);
  }

  .ui-card--interactive {
    cursor: pointer;
  }

  .ui-card--interactive:hover,
  .ui-card--interactive:focus-visible {
    transform: translateY(-2px);
    box-shadow: var(--shadow-lg);
    border-color: var(--color-border-strong);
  }
</style>
