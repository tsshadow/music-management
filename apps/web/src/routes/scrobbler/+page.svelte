<script lang="ts">
  import { onMount } from 'svelte';
  import Card from '$lib/ui/Card.svelte';
  import Button from '$lib/ui/Button.svelte';

  const apiBase = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';
  const apiPrefix = '/api/v1';

  let health: string | null = null;
  let summary: { listens?: number; artists?: number } = {};
  let status = '';

  async function fetchSummary() {
    status = 'Refreshing analyzer snapshot…';
    try {
      const [healthResp, statsResp] = await Promise.all([
        fetch(`${apiBase}${apiPrefix}/stats/health`),
        fetch(`${apiBase}${apiPrefix}/stats/overview`)
      ]);
      if (healthResp.ok) {
        const body = await healthResp.json();
        health = body.status ?? 'ok';
      }
      if (statsResp.ok) {
        summary = await statsResp.json();
      }
      status = 'Analytics refreshed';
    } catch (error) {
      console.error(error);
      status = 'Failed to reach analyzer';
    }
  }

  onMount(fetchSummary);
</script>

<section class="grid">
  <Card
    title="Library analytics"
    subtitle="Review listen counts and deduplication status from the Scrobbler backend."
  >
    <p>
      The combined backend exposes the Scrobbler REST API under <code>{apiPrefix}</code>. Use this
      dashboard to check the latest ingestion status before scheduling enrichment or export jobs.
    </p>
    <Button on:click={fetchSummary}>Refresh snapshot</Button>
  </Card>

  <Card title="Current status">
    <dl>
      <div>
        <dt>Health</dt>
        <dd>{health ?? 'unknown'}</dd>
      </div>
      <div>
        <dt>Tracked listens</dt>
        <dd>{summary.listens ?? '–'}</dd>
      </div>
      <div>
        <dt>Unique artists</dt>
        <dd>{summary.artists ?? '–'}</dd>
      </div>
    </dl>
  </Card>
</section>

<p class="status">{status}</p>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 2rem;
  }

  dl {
    display: grid;
    gap: 1.25rem;
  }

  dt {
    color: var(--color-muted);
    font-size: 0.85rem;
    text-transform: uppercase;
  }

  dd {
    margin: 0.25rem 0 0;
    font-weight: 600;
  }

  .status {
    margin-top: 2rem;
    color: var(--color-muted);
  }
</style>
