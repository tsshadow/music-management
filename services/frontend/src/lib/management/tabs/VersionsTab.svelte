<!--
  VersionsTab — the Versions page in Management (docs/designs/song-versions/).

  Every song with more than one version, the version MuMa plays, and a way to pick a
  different one (a pin), hand the choice back to the ranking, or accept a choice the
  last rescore changed. Opening a song lists each version with its source, format,
  bitrate, kind, path, rating and plays.
-->
<script>
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { RefreshCw, Layers, Pin, RotateCcw, Check, ChevronDown, ChevronRight, Star } from '@lucide/svelte';
  import { SORTS, PAGE_SIZE, pageCount, formatLabel, isChanged, uniqueTracks, songVersionsApi } from '../songVersions.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  const api = $derived(songVersionsApi(API_BASE, getHeaders));

  let items = $state([]);
  let total = $state(0);
  let page = $state(1);
  let q = $state('');
  let sort = $state('versions');
  let changedOnly = $state(false);
  let ranking = $state(null);
  let loading = $state(false);
  let busy = $state(false);
  /** The open song's work id and its loaded detail. */
  let openId = $state(null);
  let detail = $state(null);

  const pages = $derived(pageCount(total, PAGE_SIZE));

  async function load() {
    loading = true;
    try {
      const body = await api.list({ q, sort, changedOnly, page });
      items = body.items;
      total = body.total;
    } catch (e) {
      onError(e.message);
    } finally {
      loading = false;
    }
    try {
      ranking = await api.ranking();
    } catch {
      // Secondary: the list is still useful without the status line.
      ranking = null;
    }
  }

  function search() {
    page = 1;
    load();
  }

  function goTo(next) {
    page = Math.min(Math.max(1, next), pages);
    load();
  }

  async function toggle(song) {
    if (openId === song.work_id) {
      openId = null;
      detail = null;
      return;
    }
    openId = song.work_id;
    detail = null;
    try {
      detail = await api.song(song.work_id);
    } catch (e) {
      onError(e.message);
    }
  }

  /** Run a write, then reload the open song and the list so both show the new state. */
  async function act(work, run, messageKey) {
    if (busy) return;
    busy = true;
    try {
      await run();
      onMessage($t(messageKey));
      detail = await api.song(work);
      await load();
    } catch (e) {
      onError(e.message);
    } finally {
      busy = false;
    }
  }

  const pickBest = (work, trackId) => act(work, () => api.pin(work, trackId), 'management.songVersions.pinned');
  const resetAuto = (work) => act(work, () => api.pin(work, null), 'management.songVersions.reset');
  const acceptChange = (work) => act(work, () => api.dismissChange(work), 'management.songVersions.accepted');

  function kindLabel(kind) {
    return $t(`management.songVersions.kinds.${kind || 'none'}`);
  }

  onMount(load);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <Layers class="text-brand" size={32} /> {$t('management.tabs.songVersions')}
      </h2>
      <p class="text-muma-spotify-text max-w-3xl">{$t('management.songVersions.description')}</p>
      {#if ranking}
        <p class="text-muma-spotify-text text-xs mt-2" data-testid="ranking-status">
          {$t(ranking.prefer_lossless ? 'management.songVersions.rankingLossless' : 'management.songVersions.rankingLossy')}
          {#if ranking.pending_works > 0}
            · {$t('management.songVersions.pending', { count: ranking.pending_works })}
          {/if}
          {#if ranking.changed_works > 0}
            · {$t('management.songVersions.changedCount', { count: ranking.changed_works })}
          {/if}
        </p>
      {/if}
    </div>

    <button
      onclick={load}
      disabled={loading}
      aria-label={$t('common.refresh')}
      class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
    >
      <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
    </button>
  </header>

  <div class="flex flex-wrap items-center gap-3">
    <input
      type="search"
      bind:value={q}
      onkeydown={(e) => e.key === 'Enter' && search()}
      placeholder={$t('management.songVersions.search')}
      aria-label={$t('management.songVersions.search')}
      class="w-72 bg-muma-spotify-light border border-muma-spotify-panel rounded-full px-4 py-2 text-sm focus:outline-none focus:border-brand transition-colors"
    />
    <select
      bind:value={sort}
      onchange={search}
      aria-label={$t('management.songVersions.sort')}
      class="bg-muma-spotify-light border border-muma-spotify-panel rounded-full px-4 py-2 text-sm focus:outline-none focus:border-brand"
    >
      {#each SORTS as option (option)}
        <option value={option}>{$t(`management.songVersions.sorts.${option}`)}</option>
      {/each}
    </select>
    <label class="flex items-center gap-2 text-sm text-muma-spotify-text">
      <input type="checkbox" bind:checked={changedOnly} onchange={search} />
      {$t('management.songVersions.changedOnly')}
    </label>
    <span class="text-muma-spotify-text text-sm tabular-nums ml-auto">
      {$t('management.songVersions.total', { count: total })}
    </span>
  </div>

  {#if loading && items.length === 0}
    <div class="flex items-center justify-center p-20">
      <RefreshCw class="animate-spin text-brand" size={32} />
    </div>
  {:else if items.length === 0}
    <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
      <Layers size={48} class="mb-4 opacity-20" />
      <p>{$t('management.songVersions.empty')}</p>
    </div>
  {:else}
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden divide-y divide-muma-spotify-panel/30">
      {#each items as song (song.work_id)}
        <div>
          <button
            onclick={() => toggle(song)}
            aria-expanded={openId === song.work_id}
            class="w-full text-left p-4 hover:bg-white/5 transition-colors flex items-center gap-3"
          >
            {#if openId === song.work_id}<ChevronDown size={16} />{:else}<ChevronRight size={16} />{/if}
            <span class="flex-1 min-w-0">
              <span class="font-medium block truncate">{song.title}</span>
              <span class="text-muma-spotify-text text-xs block truncate">
                {song.artist ?? $t('management.songVersions.unknownArtist')}
                · {$t('management.songVersions.best')}: {song.canonical_title ?? '—'}
              </span>
            </span>
            {#if song.pinned_track_id}
              <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-brand/20 text-brand">
                {$t('management.songVersions.badgePinned')}
              </span>
            {/if}
            {#if isChanged(song)}
              <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-500">
                {$t('management.songVersions.badgeChanged')}
              </span>
            {/if}
            <span class="text-muma-spotify-text text-sm tabular-nums">
              {$t('management.songVersions.versionCount', { count: song.version_count })}
            </span>
          </button>

          {#if openId === song.work_id}
            <div class="px-4 pb-4">
              {#if !detail}
                <div class="flex justify-center p-6"><RefreshCw class="animate-spin text-brand" size={20} /></div>
              {:else}
                <div class="flex flex-wrap gap-2 mb-3">
                  {#if detail.pinned_track_id}
                    <button
                      onclick={() => resetAuto(detail.work_id)}
                      disabled={busy}
                      class="bg-muma-spotify-light text-white px-3 py-1.5 rounded-full font-bold text-xs inline-flex items-center gap-1 disabled:opacity-50"
                    >
                      <RotateCcw size={14} /> {$t('management.songVersions.resetAuto')}
                    </button>
                  {/if}
                  {#if isChanged(detail)}
                    <button
                      onclick={() => acceptChange(detail.work_id)}
                      disabled={busy}
                      class="bg-brand text-black px-3 py-1.5 rounded-full font-bold text-xs inline-flex items-center gap-1 disabled:opacity-50"
                    >
                      <Check size={14} /> {$t('management.songVersions.acceptChange')}
                    </button>
                  {/if}
                </div>
                <div class="overflow-x-auto">
                  <table class="w-full text-left text-sm">
                    <thead>
                      <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
                        <th class="p-3">{$t('management.songVersions.colVersion')}</th>
                        <th class="p-3">{$t('management.songVersions.colSource')}</th>
                        <th class="p-3">{$t('management.songVersions.colFormat')}</th>
                        <th class="p-3">{$t('management.songVersions.colKind')}</th>
                        <th class="p-3">{$t('management.songVersions.colListening')}</th>
                        <th class="p-3 text-right">{$t('management.songVersions.colActions')}</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-muma-spotify-panel/30">
                      {#each uniqueTracks(detail.versions) as version (version.track_id)}
                        <tr class="hover:bg-white/5 transition-colors" data-testid="version-row">
                          <td class="p-3">
                            <span class="font-medium block">{version.title}</span>
                            <span class="text-muma-spotify-text text-xs break-all block">{version.file_path ?? '—'}</span>
                            {#if version.is_canonical}
                              <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-brand/20 text-brand inline-block mt-1">
                                {$t('management.songVersions.badgeBest')}
                              </span>
                            {/if}
                            {#if detail.previous_canonical_track_id === version.track_id}
                              <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-500 inline-block mt-1">
                                {$t('management.songVersions.badgePrevious')}
                              </span>
                            {/if}
                          </td>
                          <td class="p-3 text-muma-spotify-text text-xs whitespace-nowrap">
                            {version.source ? $t(`management.songVersions.sources.${version.source}`) : '—'}
                          </td>
                          <td class="p-3 text-xs whitespace-nowrap tabular-nums">{formatLabel(version) || '—'}</td>
                          <td class="p-3 text-muma-spotify-text text-xs whitespace-nowrap">{kindLabel(version.version_kind)}</td>
                          <td class="p-3 text-muma-spotify-text text-xs whitespace-nowrap tabular-nums">
                            {#if version.rating}
                              <span class="inline-flex items-center gap-0.5"><Star size={12} /> {version.rating}</span> ·
                            {/if}
                            {$t('management.songVersions.plays', { count: version.plays })}
                          </td>
                          <td class="p-3 text-right">
                            {#if detail.pinned_track_id !== version.track_id}
                              <button
                                onclick={() => pickBest(detail.work_id, version.track_id)}
                                disabled={busy}
                                class="bg-muma-spotify-light text-white px-3 py-1.5 rounded-full font-bold text-xs inline-flex items-center gap-1 disabled:opacity-50"
                              >
                                <Pin size={14} /> {$t('management.songVersions.pickBest')}
                              </button>
                            {/if}
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    {#if pages > 1}
      <nav class="flex items-center justify-center gap-4 text-sm" aria-label={$t('management.songVersions.paging')}>
        <button onclick={() => goTo(page - 1)} disabled={page <= 1 || loading} class="px-3 py-1.5 rounded-full bg-muma-spotify-light disabled:opacity-50">
          {$t('management.songVersions.previous')}
        </button>
        <span class="tabular-nums text-muma-spotify-text">{$t('management.songVersions.pageOf', { page, pages })}</span>
        <button onclick={() => goTo(page + 1)} disabled={page >= pages || loading} class="px-3 py-1.5 rounded-full bg-muma-spotify-light disabled:opacity-50">
          {$t('management.songVersions.next')}
        </button>
      </nav>
    {/if}
  {/if}
</section>
