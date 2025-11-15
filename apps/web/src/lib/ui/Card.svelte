<script lang="ts">
  export type CardPadding = 'sm' | 'md' | 'lg' | 'xl';
  export type CardVariant = 'surface' | 'translucent';

  export let element: keyof HTMLElementTagNameMap = 'div';
  export let padding: CardPadding = 'lg';
  export let variant: CardVariant = 'translucent';
  export let interactive = false;
  export let className = '';

  const paddingClasses: Record<CardPadding, string> = {
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
    xl: 'px-8 py-8 md:py-10',
  };

  const variantClasses: Record<CardVariant, string> = {
    surface: 'bg-[var(--color-surface-overlay)] shadow-[var(--shadow-md)]',
    translucent: 'bg-[var(--color-surface-1)] backdrop-blur-2xl shadow-[var(--shadow-lg)]',
  };

  $: interactiveClasses =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-strong)] focus-visible:ring-offset-0';
  $: hoverClasses =
    'hover:-translate-y-0.5 hover:border-[var(--color-border-strong)] hover:shadow-[var(--shadow-lg)] focus-visible:-translate-y-0.5 focus-visible:border-[var(--color-border-strong)] focus-visible:shadow-[var(--shadow-lg)]';

  $: computedClass = [
    'ui-card relative block rounded-3xl border border-[var(--color-border-subtle)] text-inherit transition-all duration-150 ease-out',
    paddingClasses[padding],
    variantClasses[variant],
    interactive ? `cursor-pointer ${hoverClasses} ${interactiveClasses}` : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');
</script>

<svelte:element this={element} class={computedClass} {...$$restProps}>
  <slot />
</svelte:element>
