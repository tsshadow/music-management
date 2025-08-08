<script>
import { createEventDispatcher } from 'svelte';
import { getJobsContext } from '$lib/jobs-context';

const { steps, start } = getJobsContext();
let selected = '';
let repeat = false;
let repeatInterval = 0;
let breakOnExisting = false;
const dispatch = createEventDispatcher();

$: if (!selected && $steps.length > 0) {
  selected = $steps[0];
}

async function startSelected() {
  if (!selected) return;
  const options = {};
  if (repeat) {
    options.repeat = true;
    if (repeatInterval > 0) options.interval = repeatInterval;
  }
  if (breakOnExisting) options.breakOnExisting = true;
  const job = await start(selected, options);
  if (job) {
    dispatch('started', job);
  }
}
</script>

<div>
  <select bind:value={selected}>
    {#each $steps as step}
      <option value={step}>{step}</option>
    {/each}
  </select>
  <label>
    <input type="checkbox" bind:checked={repeat} /> Repeat
  </label>
  <input
    type="number"
    min="0"
    placeholder="Repeat interval"
    bind:value={repeatInterval}
    disabled={!repeat}
  />
  <label>
    <input type="checkbox" bind:checked={breakOnExisting} /> Break on existing
  </label>
  <button on:click={startSelected}>Start</button>
</div>
