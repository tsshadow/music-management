<script lang="ts">
  import { onMount } from 'svelte';
  import Card from '$lib/ui/Card.svelte';
  import Button from '$lib/ui/Button.svelte';
  import type {
    ConfigField,
    DownloadBatch,
    DownloadTask,
    ImporterJobStatus,
    JobListing,
    ManualJobResult,
    RecurringJob
  } from '$lib/types';

  const apiBase = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api';

  type SchedulePayload = {
    repeat: boolean;
    interval?: number;
    break_on_existing?: boolean | null;
    redownload?: boolean;
  };

  let apiKey = '';
  let accounts: { youtube: string[]; soundcloud: string[] } = { youtube: [], soundcloud: [] };
  let configFields: ConfigField[] = [];
  let groupedConfig: Record<string, ConfigField[]> = {};
  let pendingConfig: Record<string, unknown> = {};
  let showSettings = false;
  let downloadTask: DownloadTask = { source: 'youtube', target: '', options: {} };
  let downloadResult: DownloadBatch | null = null;
  let recurringResult: RecurringJob | null = null;
  let manualResult: ManualJobResult | null = null;
  let status = '';

  let jobListing: JobListing = { active: [], recent: [] };
  let recurringJobs: RecurringJob[] = [];

  let importRepeat = true;
  let importInterval = 3600;

  let youtubeRepeat = true;
  let youtubeInterval = 3600;
  let youtubeBreakOnExisting = true;
  let youtubeRedownload = false;

  let soundcloudRepeat = true;
  let soundcloudInterval = 3600;
  let soundcloudBreakOnExisting = true;
  let soundcloudRedownload = false;

  let tagRepeat = true;
  let tagInterval = 3600;
  let taggingKind: 'tag' | 'tag-soundcloud' | 'tag-youtube' | 'tag-telegram' | 'tag-labels' | 'tag-generic' = 'tag';

  const taggingOptions = [
    { label: 'Alles', value: 'tag' },
    { label: 'SoundCloud', value: 'tag-soundcloud' },
    { label: 'YouTube', value: 'tag-youtube' },
    { label: 'Telegram', value: 'tag-telegram' },
    { label: 'Labels', value: 'tag-labels' },
    { label: 'Generic', value: 'tag-generic' }
  ];

  let manualSource: 'youtube' | 'soundcloud' = 'youtube';
  let manualUrl = '';
  let manualBreakOnExisting = true;
  let manualRedownload = false;

  $: groupedConfig = configFields.reduce<Record<string, ConfigField[]>>((acc, field) => {
    if (!acc[field.group]) {
      acc[field.group] = [];
    }
    acc[field.group].push(field);
    return acc;
  }, {});

  onMount(() => {
    refreshAll();
  });

  async function refreshAll() {
    await Promise.all([refreshMetadata(), refreshJobs()]);
  }

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
        configFields = (data.fields ?? []) as ConfigField[];
      }
      status = 'Metadata refreshed';
    } catch (error) {
      console.error(error);
      status = 'Failed to load metadata';
    }
  }

  async function refreshJobs() {
    status = 'Loading job status…';
    try {
      const headers = apiKey ? { 'x-api-key': apiKey } : {};
      const [jobsResp, recurringResp] = await Promise.all([
        fetch(`${apiBase}/importer/jobs`, { headers }),
        fetch(`${apiBase}/importer/jobs/recurring`, { headers })
      ]);
      if (jobsResp.ok) {
        const listing = (await jobsResp.json()) as Partial<JobListing>;
        jobListing = {
          active: listing.active ?? [],
          recent: listing.recent ?? []
        };
      }
      if (recurringResp.ok) {
        recurringJobs = (await recurringResp.json()) as RecurringJob[];
      }
      status = 'Job status refreshed';
    } catch (error) {
      console.error(error);
      status = 'Failed to load job status';
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
    await refreshJobs();
    status = 'Download batch created';
  }

  async function scheduleImporterJob(kind: string, payload: SchedulePayload) {
    status = payload.repeat ? 'Scheduling recurring job…' : 'Triggering importer job…';
    recurringResult = null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (apiKey) headers['x-api-key'] = apiKey;
    const body: Record<string, unknown> = { kind, repeat: payload.repeat };
    if (payload.repeat && payload.interval !== undefined) {
      body.interval = payload.interval;
    }
    if ('break_on_existing' in payload) {
      body.break_on_existing = payload.break_on_existing;
    }
    if ('redownload' in payload) {
      body.redownload = payload.redownload;
    }
    const response = await fetch(`${apiBase}/importer/jobs/recurring`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    });
    if (!response.ok) {
      status = 'Failed to schedule importer job';
      return;
    }
    recurringResult = (await response.json()) as RecurringJob;
    await refreshJobs();
    status = payload.repeat ? 'Recurring job scheduled' : 'Importer job started';
  }

  async function submitManualJob(event: Event) {
    event.preventDefault();
    status = 'Starting manual download…';
    manualResult = null;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (apiKey) headers['x-api-key'] = apiKey;
    const response = await fetch(`${apiBase}/importer/jobs/manual`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        source: manualSource,
        url: manualUrl,
        break_on_existing: manualBreakOnExisting,
        redownload: manualRedownload
      })
    });
    if (!response.ok) {
      status = 'Manual download failed';
      return;
    }
    manualResult = await response.json();
    await refreshJobs();
    status = 'Manual download triggered';
  }

  function submitRecurringImport(event: Event) {
    event.preventDefault();
    scheduleImporterJob('import', {
      repeat: importRepeat,
      interval: importRepeat ? importInterval : undefined
    });
  }

  function submitRecurringYoutube(event: Event) {
    event.preventDefault();
    scheduleImporterJob('download-youtube', {
      repeat: youtubeRepeat,
      interval: youtubeRepeat ? youtubeInterval : undefined,
      break_on_existing: youtubeBreakOnExisting,
      redownload: youtubeRedownload
    });
  }

  function submitRecurringSoundcloud(event: Event) {
    event.preventDefault();
    scheduleImporterJob('download-soundcloud', {
      repeat: soundcloudRepeat,
      interval: soundcloudRepeat ? soundcloudInterval : undefined,
      break_on_existing: soundcloudBreakOnExisting,
      redownload: soundcloudRedownload
    });
  }

  function submitRecurringTag(event: Event) {
    event.preventDefault();
    scheduleImporterJob(taggingKind, {
      repeat: tagRepeat,
      interval: tagRepeat ? tagInterval : undefined
    });
  }

  function openSettings() {
    showSettings = true;
    pendingConfig = {};
  }

  function closeSettings() {
    showSettings = false;
    pendingConfig = {};
  }

  function updateConfigValue(field: ConfigField, raw: string | boolean) {
    let value: unknown = raw;
    if (field.type === 'integer') {
      if (typeof raw === 'string') {
        value = raw.trim() === '' ? null : Number(raw);
      }
      if (typeof value === 'number' && Number.isNaN(value)) {
        value = null;
      }
    } else if (field.type === 'boolean') {
      value = Boolean(raw);
    } else if (field.type === 'string') {
      if (typeof raw === 'string' && raw.trim() === '' && field.nullable) {
        value = null;
      } else {
        value = raw;
      }
    }

    const current = field.value ?? null;
    const normalized = value === undefined ? null : value;
    if (normalized === current || (normalized === null && current === null)) {
      const { [field.key]: _, ...rest } = pendingConfig;
      pendingConfig = rest;
    } else {
      pendingConfig = { ...pendingConfig, [field.key]: normalized };
    }
  }

  async function saveConfig(event: Event) {
    event.preventDefault();
    if (!Object.keys(pendingConfig).length) {
      closeSettings();
      return;
    }
    status = 'Updating importer configuration…';
    const headers: Record<string, string> = {
      'Content-Type': 'application/json'
    };
    if (apiKey) headers['x-api-key'] = apiKey;
    const response = await fetch(`${apiBase}/importer/config`, {
      method: 'PATCH',
      headers,
      body: JSON.stringify({ updates: pendingConfig })
    });
    if (!response.ok) {
      status = 'Failed to update configuration';
      return;
    }
    const data = await response.json();
    const values = (data.values ?? {}) as Record<string, unknown>;
    configFields = configFields.map((field) => ({
      ...field,
      value: field.key in values ? values[field.key] : field.value
    }));
    pendingConfig = {};
    showSettings = false;
    status = 'Configuration updated';
  }

  function formatLog(entry: Record<string, unknown>): string {
    const timestamp = typeof entry.timestamp === 'string' ? entry.timestamp : null;
    const details = Object.entries(entry)
      .filter(([key]) => key !== 'timestamp')
      .map(([key, value]) => {
        if (value === null || value === undefined) return `${key}: null`;
        if (typeof value === 'object') {
          return `${key}: ${JSON.stringify(value)}`;
        }
        return `${key}: ${value}`;
      });
    const summary = details.join(', ');
    return timestamp ? `${timestamp}${summary ? ` – ${summary}` : ''}` : summary;
  }

  function formatOption(value: unknown): string {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'boolean') return value ? 'true' : 'false';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }
</script>

<section class="grid importer">
  <Card title="Importer API access" subtitle="Provide an API key and explore available configuration.">
    <svelte:fragment slot="actions">
      <button class="icon-button" type="button" aria-label="Open importer settings" on:click={openSettings}>
        ⚙️
      </button>
    </svelte:fragment>
    <form class="api-access" on:submit|preventDefault={refreshMetadata}>
      <label>
        API key
        <input bind:value={apiKey} placeholder="Optional" />
      </label>
      <Button type="submit" variant="primary">Refresh metadata</Button>
    </form>
    {#if configFields.length}
      <div class="config-grid">
        {#each configFields.slice(0, 4) as field}
          <article>
            <h3>{field.key}</h3>
            <p>{field.description}</p>
            <span>{formatOption(field.value)}</span>
          </article>
        {/each}
      </div>
      <p class="hint">Open the gear menu to view and edit all importer options.</p>
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

  {#if showSettings}
    <div class="modal-backdrop" role="dialog" aria-modal="true">
      <div class="modal">
        <header class="modal-header">
          <h3>Importer settings</h3>
          <button class="icon-button close" type="button" aria-label="Close settings" on:click={closeSettings}>
            ✕
          </button>
        </header>
        <form on:submit={saveConfig}>
          <div class="modal-content">
            {#each Object.entries(groupedConfig) as [group, fields]}
              <section>
                <h4>{group}</h4>
                {#each fields as field}
                  {@const currentValue = pendingConfig[field.key] ?? field.value ?? ''}
                  <label class="setting">
                    <span>
                      <strong>{field.key}</strong>
                      <small>{field.description}</small>
                    </span>
                    {#if field.type === 'boolean'}
                      <input
                        type="checkbox"
                        checked={Boolean(pendingConfig[field.key] ?? field.value)}
                        on:change={(event) => updateConfigValue(field, (event.target as HTMLInputElement).checked)}
                      />
                    {:else if field.type === 'integer'}
                      <input
                        type="number"
                        value={currentValue === null ? '' : currentValue}
                        on:input={(event) => updateConfigValue(field, (event.target as HTMLInputElement).value)}
                        placeholder={field.nullable ? 'Optional' : ''}
                      />
                    {:else}
                      <input
                        value={currentValue === null ? '' : String(currentValue)}
                        on:input={(event) => updateConfigValue(field, (event.target as HTMLInputElement).value)}
                        placeholder={field.nullable ? 'Optional' : ''}
                      />
                    {/if}
                  </label>
                {/each}
              </section>
            {/each}
          </div>
          <footer class="modal-actions">
            <Button type="button" variant="ghost" on:click={closeSettings}>Cancel</Button>
            <Button type="submit" variant="primary">Save settings</Button>
          </footer>
        </form>
      </div>
    </div>
  {/if}

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

  <Card title="Importer jobs" subtitle="Start imports, downloads, and tagging on demand or on a schedule.">
    <div class="recurring-grid">
      <form class="panel" on:submit={submitRecurringImport}>
        <h3>Import pipeline</h3>
        <label class="checkbox">
          <input type="checkbox" bind:checked={importRepeat} /> Repeat
        </label>
        {#if importRepeat}
          <label>
            Interval (seconds)
            <input type="number" min="60" bind:value={importInterval} />
          </label>
        {/if}
        <Button type="submit">Start import</Button>
      </form>

      <form class="panel" on:submit={submitRecurringYoutube}>
        <h3>YouTube downloads</h3>
        <label class="checkbox">
          <input type="checkbox" bind:checked={youtubeRepeat} /> Repeat
        </label>
        {#if youtubeRepeat}
          <label>
            Interval (seconds)
            <input type="number" min="60" bind:value={youtubeInterval} />
          </label>
        {/if}
        <label class="checkbox">
          <input type="checkbox" bind:checked={youtubeBreakOnExisting} /> Break on existing
        </label>
        <label class="checkbox">
          <input type="checkbox" bind:checked={youtubeRedownload} /> Redownload
        </label>
        <Button type="submit">Start YouTube job</Button>
      </form>

      <form class="panel" on:submit={submitRecurringSoundcloud}>
        <h3>SoundCloud downloads</h3>
        <label class="checkbox">
          <input type="checkbox" bind:checked={soundcloudRepeat} /> Repeat
        </label>
        {#if soundcloudRepeat}
          <label>
            Interval (seconds)
            <input type="number" min="60" bind:value={soundcloudInterval} />
          </label>
        {/if}
        <label class="checkbox">
          <input type="checkbox" bind:checked={soundcloudBreakOnExisting} /> Break on existing
        </label>
        <label class="checkbox">
          <input type="checkbox" bind:checked={soundcloudRedownload} /> Redownload
        </label>
        <Button type="submit">Start SoundCloud job</Button>
      </form>

      <form class="panel" on:submit={submitRecurringTag}>
        <h3>Tagging jobs</h3>
        <label>
          Profiel
          <select bind:value={taggingKind}>
            {#each taggingOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
        </label>
        <label class="checkbox">
          <input type="checkbox" bind:checked={tagRepeat} /> Repeat
        </label>
        {#if tagRepeat}
          <label>
            Interval (seconds)
            <input type="number" min="60" bind:value={tagInterval} />
          </label>
        {/if}
        <Button type="submit">Start tagging</Button>
      </form>
    </div>

    {#if recurringResult}
      <dl class="result">
        <div>
          <dt>Scheduler</dt>
          <dd>{recurringResult.job_id ?? '—'}</dd>
        </div>
        <div>
          <dt>Kind</dt>
          <dd>{recurringResult.kind}</dd>
        </div>
        <div>
          <dt>Runs</dt>
          <dd>{recurringResult.runs}</dd>
        </div>
        <div>
          <dt>Last run</dt>
          <dd>{recurringResult.last_run_at ?? '—'}</dd>
        </div>
        <div>
          <dt>Mode</dt>
          <dd>{recurringResult.repeat ? `${recurringResult.interval ?? 0}s interval` : 'Single run'}</dd>
        </div>
        {#if recurringResult.last_job_ids.length}
          <div>
            <dt>Latest jobs</dt>
            <dd>{recurringResult.last_job_ids.join(', ')}</dd>
          </div>
        {/if}
      </dl>
    {/if}
  </Card>

  <Card title="Manual downloads" subtitle="Fetch a single URL without waiting for the next recurring run.">
    <form class="panel" on:submit={submitManualJob}>
      <label>
        Source
        <select bind:value={manualSource}>
          <option value="youtube">YouTube</option>
          <option value="soundcloud">SoundCloud</option>
        </select>
      </label>
      <label>
        URL
        <input bind:value={manualUrl} placeholder="https://example.com/track" required />
      </label>
      <label class="checkbox">
        <input type="checkbox" bind:checked={manualBreakOnExisting} /> Break on existing
      </label>
      <label class="checkbox">
        <input type="checkbox" bind:checked={manualRedownload} /> Redownload
      </label>
      <Button type="submit">Trigger manual download</Button>
    </form>
    {#if manualResult}
      <dl class="result">
        <div>
          <dt>Jobs</dt>
          <dd>{manualResult.job_ids.join(', ')}</dd>
        </div>
        <div>
          <dt>Requested</dt>
          <dd>{manualResult.requested_at}</dd>
        </div>
      </dl>
    {/if}
  </Card>

  <Card title="Job activity" subtitle="Inspect running jobs, recent history, and saved schedules.">
    <div class="status-grid">
      <section>
        <h3>Running</h3>
        {#if jobListing.active.length}
          <ul>
            {#each jobListing.active as job}
              <li>
                <strong>{job.step ?? job.id}</strong>
                <span class="meta">Started {job.started ?? '—'} · Status {job.status}</span>
                {#if job.log?.length}
                  <ul class="log">
                    {#each job.log.slice(-5) as entry}
                      <li>{formatLog(entry as Record<string, unknown>)}</li>
                    {/each}
                  </ul>
                {/if}
              </li>
            {/each}
          </ul>
        {:else}
          <p class="empty">No active jobs.</p>
        {/if}
      </section>
      <section>
        <h3>Recent jobs</h3>
        {#if jobListing.recent.length}
          <ul>
            {#each jobListing.recent.slice(0, 5) as job}
              <li>
                <strong>{job.step ?? job.id}</strong>
                <span class="meta">Finished {job.finished ?? '—'} · Status {job.status}</span>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="empty">No job history yet.</p>
        {/if}
      </section>
      <section>
        <h3>Schedules</h3>
        {#if recurringJobs.length}
          <ul>
            {#each recurringJobs as job}
              <li>
                <strong>{job.kind}</strong>
                <span class="meta">Repeat {job.repeat ? `${job.interval ?? 0}s` : 'no'} · Started {job.started_at}</span>
                {#if Object.keys(job.options ?? {}).length}
                  <dl class="options">
                    {#each Object.entries(job.options ?? {}) as [key, value]}
                      <div>
                        <dt>{key}</dt>
                        <dd>{formatOption(value)}</dd>
                      </div>
                    {/each}
                  </dl>
                {/if}
                {#if job.history.length}
                  <details>
                    <summary>Recent runs</summary>
                    <ul class="log">
                      {#each job.history.slice(-3) as run}
                        <li>
                          <strong>{run.started_at}</strong>
                          <span class="meta">Completed {run.completed_at ?? '—'}</span>
                          {#if run.details?.length}
                            <ul>
                              {#each run.details as detail}
                                <li>
                                  <span>{detail.step ?? detail.id} — {detail.status}</span>
                                  {#if detail.log?.length}
                                    <ul>
                                      {#each detail.log.slice(-3) as entry}
                                        <li>{formatLog(entry as Record<string, unknown>)}</li>
                                      {/each}
                                    </ul>
                                  {/if}
                                </li>
                              {/each}
                            </ul>
                          {/if}
                        </li>
                      {/each}
                    </ul>
                  </details>
                {/if}
              </li>
            {/each}
          </ul>
        {:else}
          <p class="empty">No recurring jobs configured.</p>
        {/if}
      </section>
    </div>
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

  .hint {
    color: var(--color-muted);
    font-size: 0.9rem;
  }

  .icon-button {
    background: none;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 999px;
    color: var(--color-text);
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 0.35rem 0.6rem;
    transition: background 0.2s ease, border-color 0.2s ease;
  }

  .icon-button:hover {
    background: rgba(148, 163, 184, 0.1);
    border-color: rgba(148, 163, 184, 0.5);
  }

  .icon-button.close {
    border: none;
    font-size: 1.25rem;
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

  .recurring-grid {
    display: grid;
    gap: 1.5rem;
  }

  .panel h3 {
    margin: 0;
    font-size: 1.05rem;
  }

  .panel h3 + label {
    margin-top: 0.5rem;
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

  .status-grid {
    display: grid;
    gap: 1.25rem;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  }

  .status-grid section {
    background: var(--color-surface-alt);
    border-radius: calc(var(--radius-base) / 1.5);
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .status-grid ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0.75rem;
  }

  .status-grid .meta {
    display: block;
    color: var(--color-muted);
    font-size: 0.85rem;
    margin-top: 0.25rem;
  }

  .status-grid .log {
    margin-top: 0.5rem;
    padding-left: 1rem;
    border-left: 2px solid rgba(148, 163, 184, 0.25);
    font-size: 0.85rem;
    display: grid;
    gap: 0.4rem;
  }

  .status-grid details {
    margin-top: 0.5rem;
  }

  .status-grid details summary {
    cursor: pointer;
    font-weight: 600;
  }

  .options {
    display: grid;
    gap: 0.25rem;
    margin-top: 0.5rem;
  }

  .options dt {
    font-size: 0.75rem;
    text-transform: uppercase;
    color: var(--color-muted);
  }

  .options dd {
    margin: 0;
    font-weight: 500;
  }

  .empty {
    color: var(--color-muted);
  }

  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.65);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    z-index: 50;
  }

  .modal {
    background: var(--color-surface);
    border-radius: var(--radius-base);
    box-shadow: var(--shadow-lg);
    width: min(720px, 100%);
    max-height: 90vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1.5rem 1.5rem 0;
  }

  .modal-content {
    padding: 0 1.5rem;
    overflow-y: auto;
    display: grid;
    gap: 1.5rem;
  }

  .modal-content section {
    display: grid;
    gap: 1rem;
  }

  .modal-content h4 {
    margin: 0;
    font-size: 1rem;
  }

  .setting {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .setting span {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .setting small {
    color: var(--color-muted);
    font-weight: 400;
  }

  .modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 1rem;
    padding: 1.5rem;
    border-top: 1px solid rgba(148, 163, 184, 0.25);
  }
</style>
