<script>
  import { onMount } from 'svelte';
  import { t, formatDateTime } from '../../i18n/index.js';
  import { Newspaper, RefreshCw, Save, Radio } from '@lucide/svelte';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let sources = $state([]);
  let bulletins = $state([]);
  let loading = $state(false);
  let saving = $state(false);
  let recording = $state(false);

  // The form edits one source at a time; there is one by default and the schema
  // allows more, so the slug stays the key everything is written against.
  let form = $state({
    slug: 'nos',
    name: '',
    stream_url: '',
    minute_of_hour: 0,
    duration_seconds: 600,
    retention_count: 12,
    enabled: true
  });
  let lastError = $state(null);
  let lastSuccessAt = $state(null);

  /** mm:ss, so a ten-minute recording reads as 10:12 rather than 612000. */
  function formatDuration(ms) {
    const total = Math.round(ms / 1000);
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${minutes}:${String(seconds).padStart(2, '0')}`;
  }

  function formatSize(bytes) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function formatMoment(epochSeconds) {
    if (!epochSeconds) return $t('management.news.never');
    return formatDateTime(epochSeconds * 1000);
  }

  async function fetchSources() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/news/sources`, { headers: getHeaders() });
      if (!res.ok) {
        onError($t('management.news.loadFailed'));
        return;
      }
      const body = await res.json();
      sources = body.sources || [];
      const source = sources[0];
      if (source) {
        form = {
          slug: source.slug,
          name: source.name,
          stream_url: source.stream_url,
          minute_of_hour: source.minute_of_hour,
          duration_seconds: source.duration_seconds,
          retention_count: source.retention_count,
          enabled: source.enabled
        };
        lastError = source.last_error;
        lastSuccessAt = source.last_success_at;
      }
    } catch {
      onError($t('management.news.loadFailed'));
    } finally {
      loading = false;
    }
  }

  async function fetchBulletins() {
    try {
      const res = await fetch(`${API_BASE}/api/news/bulletins?source=${form.slug}`, {
        headers: getHeaders()
      });
      if (res.ok) bulletins = (await res.json()).bulletins || [];
    } catch (err) {
      console.error('Kon bulletins niet ophalen:', err);
    }
  }

  async function save() {
    saving = true;
    try {
      const res = await fetch(`${API_BASE}/api/news/sources/${form.slug}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          name: form.name,
          stream_url: form.stream_url,
          minute_of_hour: Number(form.minute_of_hour),
          duration_seconds: Number(form.duration_seconds),
          retention_count: Number(form.retention_count),
          enabled: form.enabled
        })
      });
      if (res.ok) {
        onMessage($t('management.news.saved'));
        await fetchSources();
      } else {
        const body = await res.json();
        onError(body.detail || $t('management.news.loadFailed'));
      }
    } catch {
      onError($t('management.news.loadFailed'));
    } finally {
      saving = false;
    }
  }

  /**
   * Records straight away instead of waiting for the hour.
   *
   * The server answers at once and records in the background, because a capture
   * takes as long as the recording itself. So this reports that it started, not
   * that it finished: the recording shows up in the list below once it lands,
   * and a failure lands in the error line above it.
   */
  async function recordNow() {
    recording = true;
    try {
      const res = await fetch(`${API_BASE}/api/news/sources/${form.slug}/record-now`, {
        method: 'POST',
        headers: getHeaders()
      });
      const body = await res.json();
      if (res.ok && body.started) {
        onMessage($t('management.news.recordingStarted', { seconds: body.duration_seconds }));
      } else {
        onError(body.detail || $t('management.news.recordFailed'));
      }
    } catch {
      onError($t('management.news.recordFailed'));
    } finally {
      recording = false;
    }
  }

  /** The background capture cannot tell this screen it finished, so ask. */
  async function refresh() {
    await fetchSources();
    await fetchBulletins();
  }

  onMount(async () => {
    await fetchSources();
    await fetchBulletins();
  });
</script>

<div class="space-y-6">
  <div class="flex items-center gap-2">
    <Newspaper size={20} class="text-brand" />
    <h2 class="text-xl font-bold text-white">{$t('management.news.title')}</h2>
  </div>
  <p class="text-sm text-muma-spotify-text max-w-2xl">{$t('management.news.explain')}</p>

  {#if loading}
    <div class="flex justify-center py-10"><RefreshCw class="animate-spin text-brand" size={32} /></div>
  {:else}
    <div class="bg-muma-spotify-panel rounded-lg p-4 space-y-3 max-w-2xl">
      <label class="block text-sm text-muma-spotify-text">
        {$t('management.news.name')}
        <input class="w-full mt-1 bg-muma-spotify-light text-white rounded px-3 py-2" bind:value={form.name} />
      </label>
      <label class="block text-sm text-muma-spotify-text">
        {$t('management.news.streamUrl')}
        <input class="w-full mt-1 bg-muma-spotify-light text-white rounded px-3 py-2" bind:value={form.stream_url} />
      </label>
      <div class="grid grid-cols-3 gap-3">
        <label class="block text-sm text-muma-spotify-text">
          {$t('management.news.minute')}
          <input type="number" min="0" max="59" class="w-full mt-1 bg-muma-spotify-light text-white rounded px-3 py-2" bind:value={form.minute_of_hour} />
        </label>
        <label class="block text-sm text-muma-spotify-text">
          {$t('management.news.duration')}
          <input type="number" min="60" class="w-full mt-1 bg-muma-spotify-light text-white rounded px-3 py-2" bind:value={form.duration_seconds} />
        </label>
        <label class="block text-sm text-muma-spotify-text">
          {$t('management.news.retention')}
          <input type="number" min="1" class="w-full mt-1 bg-muma-spotify-light text-white rounded px-3 py-2" bind:value={form.retention_count} />
        </label>
      </div>
      <label class="flex items-center gap-2 text-sm text-muma-spotify-text">
        <input type="checkbox" bind:checked={form.enabled} />
        {$t('management.news.enabled')}
      </label>

      <div class="flex items-center gap-3 pt-2">
        <button
          class="flex items-center gap-2 bg-brand text-black font-bold rounded-full px-4 py-2 cursor-pointer border-none disabled:opacity-50"
          onclick={save}
          disabled={saving}
        >
          <Save size={16} />
          {$t('management.news.save')}
        </button>
        <button
          class="flex items-center gap-2 bg-transparent text-white border border-white/20 rounded-full px-4 py-2 cursor-pointer disabled:opacity-50"
          onclick={recordNow}
          disabled={recording}
        >
          <Radio size={16} />
          {recording ? $t('management.news.recording') : $t('management.news.recordNow')}
        </button>
      </div>

      <div class="text-xs text-muma-spotify-text pt-2">
        <div>{$t('management.news.lastSuccess')}: {formatMoment(lastSuccessAt)}</div>
        {#if lastError}
          <div class="text-red-400">{$t('management.news.lastError')}: {lastError}</div>
        {/if}
      </div>
    </div>

    <div class="max-w-2xl">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-sm font-bold text-white">{$t('management.news.bulletins')}</h3>
        <button
          class="flex items-center gap-1 bg-transparent text-muma-spotify-text border-none cursor-pointer text-xs hover:text-white"
          onclick={refresh}
        >
          <RefreshCw size={14} />
          {$t('management.news.refresh')}
        </button>
      </div>
      {#if bulletins.length === 0}
        <p class="text-sm text-muma-spotify-text">{$t('management.news.noBulletins')}</p>
      {:else}
        <ul class="divide-y divide-white/5">
          {#each bulletins as bulletin (bulletin.id)}
            <li class="flex items-center justify-between py-2 text-sm text-white">
              <span>{formatMoment(bulletin.started_at)}</span>
              <span class="text-muma-spotify-text">{formatDuration(bulletin.duration_ms)} · {formatSize(bulletin.size_bytes)}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>
