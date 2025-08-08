<script>
import { onMount } from 'svelte';

const API_BASE = import.meta.env.VITE_API_BASE || '';
const WS_URL = (API_BASE ? API_BASE.replace(/^http/, 'ws').replace(/\/?api$/, '') : window.location.origin.replace(/^http/, 'ws')) + '/ws/jobs';

let jobs = [];

function upsert(job) {
  const idx = jobs.findIndex(j => j.id === job.id);
  if (['done', 'error'].includes(job.status)) {
    if (idx >= 0) jobs.splice(idx, 1);
  } else {
    if (idx >= 0) jobs[idx] = job;
    else jobs = [job, ...jobs];
  }
}

onMount(async () => {
  const res = await fetch(`${API_BASE}/jobs`);
  const data = await res.json();
  jobs = data.jobs.filter(j => ['queued', 'running'].includes(j.status));
  const ws = new WebSocket(WS_URL);
  ws.onmessage = (ev) => {
    const update = JSON.parse(ev.data);
    upsert(update);
  };
});
</script>

<h2>Running Jobs</h2>
<ul>
  {#each jobs as job}
    <li>{job.step} – {job.id}</li>
  {/each}
</ul>
