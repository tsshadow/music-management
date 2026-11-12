<script>
  /** The library's week: a 7 by 24 grid, each cell as bright as its share of the busiest hour. */
  import { barPercent } from './wrapped.js';
  import CardFrame from './CardFrame.svelte';

  const { face, tint = null, onshare = null } = $props();

  const matrix = $derived(face.matrix ?? []);
  const peak = $derived(Math.max(0, ...matrix.flat()));
</script>

<CardFrame {face} {tint} {onshare}>
  <div class="flex flex-col gap-[2px]" data-testid="wrapped-heatmap">
    {#each matrix as row, day (day)}
      <div class="grid grid-cols-[2.5rem_repeat(24,1fr)] gap-[2px] items-center">
        <span class="text-xs text-white/60 truncate">{(face.rowLabels?.[day] ?? '').slice(0, 2)}</span>
        {#each row as value, hour (hour)}
          <span
            class="block aspect-square rounded-[2px] bg-brand"
            style="opacity: {0.08 + (barPercent(value, peak) / 100) * 0.92}"
          ></span>
        {/each}
      </div>
    {/each}
  </div>
</CardFrame>
