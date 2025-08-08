<script>
import { onMount } from 'svelte';
import { getJobsContext } from '$lib/jobs-context';

const { jobs, stop, get } = getJobsContext();
let selected = null;
let now = Date.now();

onMount(() => {
  const interval = setInterval(() => {
    now = Date.now();
  }, 1000);
  return () => clearInterval(interval);
});

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
  selected = await get(id);
}
</script>

<h2>Running Jobs</h2>
<ul>
  {#each $jobs as job}
    <li>
      <button on:click={() => select(job.id)}>{job.step} – {job.id}</button>
      <div>Started: {job.started ? new Date(job.started).toLocaleString() : '-'}</div>
      <div>Duration: {duration(job)}</div>
      <button on:click={() => stop(job.id)}>Stop</button>
    </li>
  {/each}
</ul>

{#if selected}
  <h3>Job Log</h3>
  <pre>{selected.log?.join('\n') ?? ''}</pre>
{/if}
