<script>
  /**
   * Horizontal bars: one row per form, month, device, decade and so on. A card with two series
   * (your tempo against the library's, SoundCloud against YouTube) draws two bars per row and a
   * legend.
   */
  import { barPercent } from './wrapped.js';
  import CardFrame from './CardFrame.svelte';

  const { face, tint = null, onshare = null } = $props();

  const rows = $derived(face.bars ?? []);
  const peak = $derived(
    Math.max(0, ...rows.map((row) => Math.max(Number(row.value) || 0, Number(row.value2) || 0))),
  );
  const twoSeries = $derived(Array.isArray(face.series) && face.series.length === 2);
</script>

<CardFrame {face} {tint} {onshare}>
  {#if twoSeries}
    <div class="flex gap-4 text-xs text-white/80" data-testid="wrapped-legend">
      <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-brand"></span>{face.series[0]}</span>
      <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-white/50"></span>{face.series[1]}</span>
    </div>
  {/if}
  <ul class="m-0 p-0 list-none flex flex-col gap-2">
    {#each rows as row, index (index)}
      <li class="grid grid-cols-[5rem_1fr_auto] items-center gap-2 text-sm">
        <span class="truncate text-white/80">{row.label}</span>
        <span class="flex flex-col gap-0.5">
          <span class="block h-3 rounded-sm bg-brand" style="width: {barPercent(row.value, peak)}%"></span>
          {#if twoSeries}
            <span class="block h-3 rounded-sm bg-white/50" style="width: {barPercent(row.value2, peak)}%"></span>
          {/if}
        </span>
        <span class="text-right text-white/70 whitespace-nowrap">
          {row.text}{#if twoSeries} / {row.text2}{/if}
        </span>
      </li>
    {/each}
  </ul>
</CardFrame>
