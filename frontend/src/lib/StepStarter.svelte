<script>
import { createEventDispatcher } from 'svelte';
import { getJobsContext } from '$lib/jobs-context';

const { steps, start } = getJobsContext();
let selected = '';
const dispatch = createEventDispatcher();

$: if (!selected && $steps.length > 0) {
  selected = $steps[0];
}

async function startSelected() {
  if (!selected) return;
  const job = await start(selected);
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
  <button on:click={startSelected}>Start</button>
</div>
