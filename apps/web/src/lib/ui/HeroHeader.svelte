<script lang="ts">
  export let title: string;
  export let description: string;
  export let align: 'center' | 'start' = 'center';
</script>

<header
  class={`ui-hero relative isolate flex flex-col overflow-hidden px-4 py-24 text-[var(--color-text-primary)] sm:px-6 md:py-32 ${
    align === 'start' ? 'items-start text-left' : 'items-center text-center'
  }`}
>
  <div class="absolute inset-0 -z-10 bg-[var(--gradient-hero)] opacity-70 blur-3xl" aria-hidden="true"></div>
  <div
    class={`relative z-10 flex max-w-3xl flex-col gap-4 ${
      align === 'start' ? 'items-start text-left' : 'items-center text-center'
    }`}
  >
    <slot name="eyebrow" />
    <h1 class="m-0 text-[clamp(2.5rem,4vw,4rem)] font-semibold leading-[var(--line-height-tight)]">{title}</h1>
    <p class="m-0 text-lg leading-[var(--line-height-snug)] text-[var(--color-text-muted)]">{description}</p>
    <slot />
  </div>
</header>

<style>
  :global(.ui-hero [slot='eyebrow']) {
    display: inline-block;
    margin-bottom: var(--space-xs);
    text-transform: uppercase;
    letter-spacing: 0.35em;
    font-size: var(--font-size-xs);
    color: var(--color-text-soft);
  }
</style>
