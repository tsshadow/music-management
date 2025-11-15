<script lang="ts">
  import Card from './Card.svelte';

  export let label: string;
  export let value: string | number;
  export let helper: string | null = null;
</script>

<Card
  padding="xl"
  className="ui-kpi-card flex flex-col items-center text-[var(--color-text-primary)]"
>
  <p class="mb-2 text-center text-[var(--color-text-soft)] text-xs font-semibold uppercase tracking-[0.28em]">
    {label}
  </p>
  <p class="text-center text-[clamp(2.5rem,4vw,4rem)] font-bold leading-[var(--line-height-tight)]">
    {value}
  </p>
  {#if helper}
    <p class="mt-3 text-center text-sm text-[var(--color-text-muted)]">{helper}</p>
  {/if}
</Card>
