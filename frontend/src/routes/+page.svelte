<script>
  import { onMount } from 'svelte';

  const API_BASE = import.meta.env.VITE_API_BASE || '';
  const WS_URL = (API_BASE ? API_BASE.replace(/^http/, 'ws').replace(/\/?api$/, '') : window.location.origin.replace(/^http/, 'ws')) + '/ws/jobs';

  let steps = [];
  let selected = '';
  let jobs = [];
  let active = [];
  let done = [];

  let showModal = false;
  let modalLog = '';
  let modalJob = null;

  function splitJobs() {
    active = jobs.filter(j => ['queued', 'running'].includes(j.status));
    done = jobs.filter(j => ['done', 'error'].includes(j.status));
  }

  async function loadSteps() {
    const res = await fetch(`${API_BASE}/steps`);
    const data = await res.json();
    steps = data.steps;
    selected = steps[0] || '';
  }

  async function loadJobs() {
    const res = await fetch(`${API_BASE}/jobs`);
    const data = await res.json();
    jobs = data.jobs;
    splitJobs();
  }

  async function start() {
    if (!selected) return;
    const res = await fetch(`${API_BASE}/run/${selected}`, { method: 'POST' });
    const job = await res.json();
    jobs = [job, ...jobs];
    splitJobs();
  }

  async function showLog(id) {
    const res = await fetch(`${API_BASE}/job/${id}`);
    modalJob = await res.json();
    modalLog = modalJob.log.join('\n');
    showModal = true;
  }

  onMount(() => {
    loadSteps();
    loadJobs();
    const ws = new WebSocket(WS_URL);
    ws.onmessage = (ev) => {
      const update = JSON.parse(ev.data);
      const idx = jobs.findIndex(j => j.id === update.id);
      if (idx >= 0) {
        jobs[idx] = { ...jobs[idx], ...update };
      } else {
        jobs = [update, ...jobs];
      }
      splitJobs();
    };
  });
</script>

<h1>Music Importer</h1>

<div>
  <select bind:value={selected}>
    {#each steps as step}
      <option value={step}>{step}</option>
    {/each}
  </select>
  <button on:click={start}>Run</button>
</div>

<h2>Active Jobs</h2>
<ul>
  {#each active as job}
    <li on:click={() => showLog(job.id)}>{job.step} – {job.status}</li>
  {/each}
</ul>

<h2>Completed Jobs</h2>
<ul>
  {#each done as job}
    <li on:click={() => showLog(job.id)}>{job.step} – {job.status}</li>
  {/each}
</ul>

{#if showModal}
  <div class="modal">
    <div class="content">
      <h3>{modalJob.step} – {modalJob.status}</h3>
      <pre>{modalLog}</pre>
      <button on:click={() => (showModal = false)}>Close</button>
    </div>
  </div>
{/if}

<style>
  .modal {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    justify-content: center;
    align-items: center;
  }
  .content {
    background: white;
    padding: 1rem;
    max-width: 80%;
    max-height: 80%;
    overflow: auto;
  }
  ul li { cursor: pointer; }
</style>
