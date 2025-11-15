<script lang="ts">
  import { onMount } from 'svelte';
  import Card from '$lib/ui/Card.svelte';
  import Button from '$lib/ui/Button.svelte';
  import type { DownloadBatch, DownloadTask, TaggingReport } from '$lib/types';

  const apiBase = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api';

  let apiKey = '';
  let accounts: { youtube: string[]; soundcloud: string[] } = { youtube: [], soundcloud: [] };
  let configFields: { key: string; description: string; group: string }[] = [];
  let downloadTask: DownloadTask = { source: 'youtube', target: '', options: {} };
  let downloadResult: DownloadBatch | null = null;
  let taggingPayload = { profile: 'generic', tracks: [], dry_run: true };
  let taggingResult: TaggingReport | null = null;
  let status = '';

  onMount(() => {
    refreshMetadata();
  });

  async function refreshMetadata() {
    status = 'Loading importer metadata…';
    try {
      const headers = apiKey ? { 'x-api-key': apiKey } : {};
      const [accountsResp, configResp] = await Promise.all([
        fetch(`${apiBase}/importer/accounts`, { headers }),
        fetch(`${apiBase}/importer/config`, { headers })
      ]);
      if (accountsResp.ok) {
        accounts = await accountsResp.json();
      }
      if (configResp.ok) {
        const data = await configResp.json();
        configFields = data.fields ?? [];
      }
      status = 'Metadata refreshed';
    } catch (error) {
      console.error(error);
      status = 'Failed to load metadata';
    }
  }

  async function submitDownload(event: Event) {
    event.preventDefault();
    status = 'Scheduling download…';
    downloadResult = null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (apiKey) headers['x-api-key'] = apiKey;
    const body = JSON.stringify([downloadTask]);
    const response = await fetch(`${apiBase}/importer/downloads`, {
      method: 'POST',
      headers,
      body
    });
    if (!response.ok) {
      status = 'Download request failed';
      return;
    }
    downloadResult = await response.json();
    status = 'Download batch created';
  }

  async function submitTagging(event: Event) {
    event.preventDefault();
    status = 'Scheduling tagging…';
    taggingResult = null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (apiKey) headers['x-api-key'] = apiKey;
    const response = await fetch(`${apiBase}/importer/tagging`, {
      method: 'POST',
      headers,
      body: JSON.stringify(taggingPayload)
    });
    if (!response.ok) {
      status = 'Tagging request failed';
      return;
    }
    taggingResult = await response.json();
    status = 'Tagging batch created';
  }
</script>

<section class="grid importer">
  <Card title="Importer API access" subtitle="Provide an API key and explore available configuration.">
    <form class="api-access" on:submit|preventDefault={refreshMetadata}>
      <label>
        API key
        <input bind:value={apiKey} placeholder="Optional" />
      </label>
      <Button type="submit" variant="primary">Refresh metadata</Button>
    </form>
    {#if configFields.length}
      <div class="config-grid">
        {#each configFields.slice(0, 6) as field}
          <article>
            <h3>{field.key}</h3>
            <p>{field.description}</p>
            <span>{field.group}</span>
          </article>
        {/each}
      </div>
    {/if}
    {#if accounts.youtube.length || accounts.soundcloud.length}
      <div class="accounts">
        <strong>Available accounts</strong>
        <div>
          <span>YouTube:</span> {accounts.youtube.slice(0, 5).join(', ') || '—'}
        </div>
        <div>
          <span>SoundCloud:</span> {accounts.soundcloud.slice(0, 5).join(', ') || '—'}
        </div>
      </div>
    {/if}
  </Card>

  <Card title="Schedule downloads" subtitle="Trigger the new download service for a single source.">
    <form class="panel" on:submit={submitDownload}>
      <label>
        Source
        <select bind:value={downloadTask.source}>
          <option value="youtube">YouTube</option>
          <option value="manual">Manual YouTube</option>
          <option value="soundcloud">SoundCloud</option>
          <option value="telegram">Telegram</option>
        </select>
      </label>
      <label>
        Target (account or URL)
        <input bind:value={downloadTask.target} placeholder="Channel name or link" />
      </label>
      <Button type="submit">Queue download</Button>
    </form>
    {#if downloadResult}
      <dl class="result">
        <div>
          <dt>Job</dt>
          <dd>{downloadResult.job_id}</dd>
        </div>
        <div>
          <dt>Tracks planned</dt>
          <dd>{downloadResult.tracks.length}</dd>
        </div>
      </dl>
    {/if}
  </Card>

  <Card title="Apply tagging" subtitle="Send downloaded tracks to the tagging service.">
    <form class="panel" on:submit={submitTagging}>
      <label>
        Profile
        <select bind:value={taggingPayload.profile}>
          <option value="generic">Generic</option>
          <option value="youtube">YouTube</option>
          <option value="soundcloud">SoundCloud</option>
          <option value="telegram">Telegram</option>
        </select>
      </label>
      <label>
        Track locations (comma separated)
        <input
          placeholder="/music/track-1.flac, /music/track-2.flac"
          on:change={(event) => {
            const value = (event.target as HTMLInputElement).value;
            taggingPayload.tracks = value
              .split(',')
              .map((entry) => entry.trim())
              .filter(Boolean)
              .map((location) => ({ source: 'manual', location, metadata: {} }));
          }}
        />
      </label>
      <label class="checkbox">
        <input type="checkbox" bind:checked={taggingPayload.dry_run} /> Dry run
      </label>
      <Button type="submit" variant="primary">Queue tagging</Button>
    </form>
    {#if taggingResult}
      <dl class="result">
        <div>
          <dt>Job</dt>
          <dd>{taggingResult.job_id}</dd>
        </div>
        <div>
          <dt>Mutations</dt>
          <dd>{taggingResult.mutations.length}</dd>
        </div>
      </dl>
    {/if}
  </Card>
</section>

<p class="status">{status}</p>

<style>
  .importer {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 2rem;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    font-weight: 600;
  }

  input,
  select {
    border-radius: calc(var(--radius-base) / 2);
    border: 1px solid rgba(148, 163, 184, 0.25);
    padding: 0.75rem;
    background: var(--color-surface-alt);
    color: var(--color-text);
  }

  .config-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1.25rem;
  }

  .config-grid article {
    background: var(--color-surface-alt);
    padding: 1rem;
    border-radius: calc(var(--radius-base) / 1.5);
  }

  .config-grid span {
    color: var(--color-muted);
    font-size: 0.85rem;
  }

  .accounts {
    display: grid;
    gap: 0.25rem;
    font-size: 0.95rem;
  }

  .accounts span {
    color: var(--color-muted);
    margin-right: 0.35rem;
  }

  .panel {
    align-items: flex-start;
  }

  .checkbox {
    flex-direction: row;
    align-items: center;
    gap: 0.75rem;
  }

  .checkbox input {
    width: auto;
  }

  .result {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.75rem;
  }

  .result dt {
    font-size: 0.85rem;
    text-transform: uppercase;
    color: var(--color-muted);
  }

  .result dd {
    margin: 0;
    font-weight: 600;
  }

  .status {
    margin-top: 2rem;
    color: var(--color-muted);
  }
</style>
