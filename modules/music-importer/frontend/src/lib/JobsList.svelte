<script>
import { onMount, onDestroy } from 'svelte';
import { getJobsContext } from '$lib/jobs-context';

const { jobs, stop, get } = getJobsContext();
let selected = null;
let selectedId = null;
let now = Date.now();
let logInterval;

onMount(() => {
  const interval = setInterval(() => {
    now = Date.now();
  }, 1000);
  return () => clearInterval(interval);
});

$: {
  clearInterval(logInterval);
  if (selectedId && (!selected || !selected.ended)) {
    logInterval = setInterval(async () => {
      const id = selectedId;
      const job = await get(id);
      if (selectedId === id) {
        selected = job;
      }
    }, 1000);
  }
}

onDestroy(() => clearInterval(logInterval));

function duration(job) {
  if (!job.started) return '-';
  const start = new Date(job.started).getTime();
  const end = job.ended ? new Date(job.ended).getTime() : now;
  const seconds = Math.floor((end - start) / 1000);
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

async function select(id) {
  if (selectedId === id) {
    selectedId = null;
    selected = null;
    return;
  }
  selectedId = id;
  const job = await get(id);
  if (selectedId === id) {
    selected = job;
  }
}
</script>

<div class="space-y-4 rounded border border-green-700/40 bg-black/60 p-4">
  <h2 class="text-xl font-bold text-green-400">Running Jobs</h2>
  <ul class="space-y-2">
    {#each $jobs as job}
      <li class="rounded border border-green-700/40 bg-gray-900/60 p-2">
        <button
          class="mb-2 rounded bg-blue-600 px-2 py-1 text-sm font-bold text-white hover:bg-blue-500"
          on:click={() => select(job.id)}
        >
          {job.step} – {job.id}
        </button>
        <div>Started: {job.started ? new Date(job.started).toLocaleString() : '-'}</div>
        <div>Duration: {duration(job)}</div>
        <button
          class="mt-2 rounded bg-red-600 px-2 py-1 text-sm font-bold text-white hover:bg-red-500"
          on:click={() => stop(job.id)}
        >
          Stop
        </button>
      </li>
    {/each}
  </ul>

  {#if selected}
    <div class="mt-4">
      <h3 class="mb-2 text-lg font-bold text-green-400">Job Log</h3>
      <pre
        class="min-h-64 max-h-[calc(100vh-20rem)] overflow-auto rounded border border-green-700 bg-black p-2 text-green-400"
        >{selected.log?.join(String.fromCharCode(10)) ?? ''}</pre
      >
    </div>
  {/if}
</div>
