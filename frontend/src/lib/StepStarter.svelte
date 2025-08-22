<script>
import { createEventDispatcher } from 'svelte';
import { getJobsContext } from '$lib/jobs-context';

const { steps, start } = getJobsContext();
let selected = '';
let repeat = false;
let repeatInterval = 0;
let breakOnExisting = false;
let youtubeUrl = '';
const breakOnExistingSteps = ['download', 'download-soundcloud', 'download-youtube'];
const dispatch = createEventDispatcher();

$: if (!selected && $steps.length > 0) {
  selected = $steps[0];
}

$: if (!breakOnExistingSteps.includes(selected)) {
  breakOnExisting = false;
}

async function startSelected() {
  if (!selected) return;
  const options = {};
  if (repeat) {
    options.repeat = true;
    if (repeatInterval > 0) options.interval = repeatInterval;
  }
  if (breakOnExisting && breakOnExistingSteps.includes(selected))
    options.breakOnExisting = true;
  if (selected === 'manual-youtube' && youtubeUrl) options.url = youtubeUrl;
  const job = await start(selected, options);
  if (job) {
    dispatch('started', job);
  }
}
</script>

<div class="space-y-4 rounded border border-green-700/40 bg-black/60 p-4">
  <select
    class="rounded border border-green-700 bg-gray-900 p-2 text-green-400"
    bind:value={selected}
  >
    {#each $steps as step}
      <option value={step}>{step}</option>
    {/each}
  </select>
  <label class="ml-2 inline-flex items-center gap-2 text-sm">
    <input
      class="h-4 w-4 rounded border-green-700 bg-gray-900 text-green-500"
      type="checkbox"
      bind:checked={repeat}
    />
    Repeat
  </label>
  <input
    class="rounded border border-green-700 bg-gray-900 p-2 text-green-400 disabled:opacity-50"
    type="number"
    min="0"
    placeholder="Repeat interval"
    bind:value={repeatInterval}
    disabled={!repeat}
  />
  {#if breakOnExistingSteps.includes(selected)}
    <label class="ml-2 inline-flex items-center gap-2 text-sm">
      <input
        class="h-4 w-4 rounded border-green-700 bg-gray-900 text-green-500"
        type="checkbox"
        bind:checked={breakOnExisting}
      />
      Break on existing
    </label>
  {/if}
  {#if selected === 'manual-youtube'}
    <input
      class="rounded border border-green-700 bg-gray-900 p-2 text-green-400"
      type="text"
      placeholder="YouTube URL"
      bind:value={youtubeUrl}
    />
  {/if}
  <button
    class="rounded bg-green-600 px-4 py-2 font-bold text-black shadow hover:bg-green-500"
    on:click={startSelected}
  >
    Start
  </button>
</div>
