<script lang="ts">
  import Card from './Card.svelte';

  export let label: string;
  export let value: string | number;
  export let helper: string | null = null;
</script>

<Card className="ui-kpi-card" padding="xl">
  <p class="ui-kpi-card__label">{label}</p>
  <p class="ui-kpi-card__value">{value}</p>
  {#if helper}
    <p class="ui-kpi-card__helper">{helper}</p>
  {/if}
</Card>

<style>
  :global(.ui-kpi-card) {
    text-align: center;
    color: var(--color-text-primary);
  }

  .ui-kpi-card__label {
    margin: 0 0 var(--space-xs);
    text-transform: uppercase;
    letter-spacing: 0.28em;
    font-size: var(--font-size-xs);
    color: var(--color-text-soft);
  }

  .ui-kpi-card__value {
    margin: 0;
    font-size: var(--font-size-2xl);
    font-weight: 700;
    line-height: var(--line-height-tight);
  }

  .ui-kpi-card__helper {
    margin: var(--space-sm) 0 0;
    font-size: var(--font-size-sm);
    color: var(--color-text-muted);
  }
</style>
