<script>
import { onMount, createEventDispatcher } from 'svelte';

const API_BASE = import.meta.env.VITE_API_BASE || '';
let steps = [];
let selected = '';
const dispatch = createEventDispatcher();

async function loadSteps() {
  const res = await fetch(`${API_BASE}/steps`);
  const data = await res.json();
  steps = data.steps;
  selected = steps[0] || '';
}

async function start() {
  if (!selected) return;
  const res = await fetch(`${API_BASE}/run/${selected}`, { method: 'POST' });
  const job = await res.json();
  dispatch('started', job);
}

onMount(loadSteps);
</script>

<div>
  <select bind:value={selected}>
    {#each steps as step}
      <option value={step}>{step}</option>
    {/each}
  </select>
  <button on:click={start}>Start</button>
</div>
