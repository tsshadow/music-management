<script>
  /** Your clock: listens per hour of the day as 24 columns, and per weekday underneath. */
  import { barPercent } from './wrapped.js';
  import CardFrame from './CardFrame.svelte';

  const { face, tint = null, onshare = null } = $props();

  const hours = $derived(face.hours ?? []);
  const weekdays = $derived(face.weekdays ?? []);
  const hourPeak = $derived(Math.max(0, ...hours.map((entry) => entry.value)));
  const dayPeak = $derived(Math.max(0, ...weekdays.map((entry) => entry.value)));
</script>

<CardFrame {face} {tint} {onshare}>
  <div class="flex items-end gap-[2px] h-32" data-testid="wrapped-hours">
    {#each hours as entry, index (index)}
      <span
        class="flex-1 rounded-t-sm bg-brand min-h-[2px]"
        style="height: {barPercent(entry.value, hourPeak)}%"
        title="{entry.label}: {entry.text}"
      ></span>
    {/each}
  </div>
  <div class="flex justify-between text-xs text-white/60">
    <span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>23:00</span>
  </div>
  <ul class="m-0 p-0 list-none flex flex-col gap-1">
    {#each weekdays as entry, index (index)}
      <li class="grid grid-cols-[6rem_1fr_auto] items-center gap-2 text-sm">
        <span class="text-white/80">{entry.label}</span>
        <span class="block h-2 rounded-sm bg-white/60" style="width: {barPercent(entry.value, dayPeak)}%"></span>
        <span class="text-right text-white/70">{entry.text}</span>
      </li>
    {/each}
  </ul>
</CardFrame>
