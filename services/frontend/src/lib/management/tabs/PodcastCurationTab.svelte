<script>
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import {
    RefreshCw,
    Search,
    Check,
    X,
    Merge,
    Podcast,
    CircleSlash,
    CircleCheck,
    HelpCircle
  } from '@lucide/svelte';
  import {
    WHITE,
    BLACK,
    UNKNOWN,
    STATE_FILTERS,
    filterPodcasts,
    summarize,
    describeOutcome,
    describeDecision,
    describeEpisodes,
    extraAliases,
    buildDecision,
    mergeTargets
  } from '../podcastCuration.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let rows = $state([]);
  let whiteShows = $state([]);
  let loading = $state(false);
  let stateFilter = $state(UNKNOWN);
  let search = $state('');

  // The row being decided in the modal, plus the decision being composed for it.
  let deciding = $state(null);
  let decisionState = $state(WHITE);
  let decisionMergeId = $state('');
  let decisionHost = $state('');
  let decisionStation = $state('');

  const visibleRows = $derived(filterPodcasts(rows, search));
  const counts = $derived(summarize(rows));
  const targets = $derived(mergeTargets(whiteShows, deciding?.id));
  const pendingDecision = $derived(
    deciding
      ? buildDecision({
          podcastId: deciding.id,
          state: decisionState,
          mergeIntoId: decisionMergeId,
          host: decisionHost,
          station: decisionStation
        })
      : { valid: false, error: null }
  );

  async function fetchPodcasts() {
    loading = true;
    try {
      const query = stateFilter === 'all' ? '' : `state=${stateFilter}&`;
      const res = await fetch(`${API_BASE}/api/rules/podcasts?${query}limit=500`, {
        headers: getHeaders()
      });
      if (res.ok) {
        rows = await res.json();
      } else {
        onError($t('management.podcasts.loadFailed'));
      }
    } catch (err) {
      onError($t('management.podcasts.loadNetworkError'));
    } finally {
      loading = false;
    }
  }

  /**
   * The approved shows, kept separate from the table: they are the only valid
   * merge targets, and stay needed while the table shows the unknown queue.
   */
  async function fetchWhiteShows() {
    try {
      const res = await fetch(`${API_BASE}/api/rules/podcasts?state=${WHITE}&limit=1000`, {
        headers: getHeaders()
      });
      if (res.ok) whiteShows = await res.json();
    } catch (err) {
      console.error('Kon goedgekeurde shows niet ophalen:', err);
    }
  }

  async function decide(rowToDecide, state, options = {}) {
    const decision = buildDecision({ podcastId: rowToDecide.id, state, ...options });
    if (!decision.valid) {
      onError(decision.error);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/rules/podcasts/${rowToDecide.id}/decide`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(decision.payload)
      });
      if (res.ok) {
        const mergedInto = decision.payload.merge_into_podcast_id;
        if (mergedInto) {
          const target = whiteShows.find((show) => Number(show.id) === Number(mergedInto));
          onMessage(`${rowToDecide.name} hoort nu bij ${target?.name ?? 'de andere show'}.`);
        } else {
          onMessage(`${rowToDecide.name} ${state === WHITE ? 'goedgekeurd' : 'afgekeurd'}.`);
        }
        deciding = null;
        await Promise.all([fetchPodcasts(), fetchWhiteShows()]);
      } else {
        const data = await res.json();
        onError(data.detail || $t('management.podcasts.saveFailed'));
      }
    } catch (err) {
      onError($t('management.podcasts.saveNetworkError'));
    }
  }

  function openDecision(rowToDecide) {
    deciding = rowToDecide;
    decisionState = rowToDecide.state === UNKNOWN ? WHITE : rowToDecide.state;
    decisionMergeId = '';
    decisionHost = rowToDecide.host ?? '';
    decisionStation = rowToDecide.station ?? '';
  }

  $effect(() => {
    if (stateFilter) fetchPodcasts();
  });

  onMount(fetchWhiteShows);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <Podcast class="text-spotify-green" size={32} /> {$t('management.tabs.podcastCuration')}
      </h2>
      <p class="text-spotify-lightgray">
        {$t('management.podcasts.subtitle')}
      </p>
    </div>

    <div class="flex bg-spotify-gray p-1 rounded-full border border-white border-opacity-5">
      {#each STATE_FILTERS as filter (filter.id)}
        <button
          class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {stateFilter === filter.id ? 'bg-white text-black' : 'text-spotify-lightgray hover:text-white'}"
          onclick={() => (stateFilter = filter.id)}
        >
          {filter.label}
        </button>
      {/each}
    </div>
  </header>

  <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
    <div class="p-6 bg-black bg-opacity-20 flex justify-between items-center gap-4 flex-wrap">
      <h3 class="text-xl font-bold flex items-center gap-2">
        {#if stateFilter === UNKNOWN}<HelpCircle size={20} class="text-yellow-500" />{/if}
        {#if stateFilter === WHITE}<CircleCheck size={20} class="text-spotify-green" />{/if}
        {#if stateFilter === BLACK}<CircleSlash size={20} class="text-red-500" />{/if}
        {STATE_FILTERS.find((f) => f.id === stateFilter)?.label}
        <span class="text-spotify-lightgray text-sm font-normal">({counts.total})</span>
      </h3>

      <div class="flex items-center gap-3">
        <div class="relative">
          <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-spotify-lightgray" />
          <input
            type="text"
            bind:value={search}
            placeholder={$t('management.podcasts.searchPlaceholder')}
            aria-label={$t('management.podcasts.searchLabel')}
            class="bg-spotify-dark border border-spotify-gray rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-spotify-green transition-colors"
          />
        </div>
        <button
          onclick={fetchPodcasts}
          disabled={loading}
          aria-label={$t('common.refresh')}
          class="text-spotify-lightgray hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
        </button>
      </div>
    </div>

    <div class="min-h-[200px]">
      {#if loading && rows.length === 0}
        <div class="flex items-center justify-center p-20">
          <RefreshCw class="animate-spin text-spotify-green" size={32} />
        </div>
      {:else if visibleRows.length === 0}
        <div class="flex flex-col items-center justify-center p-20 text-spotify-lightgray">
          <Podcast size={48} class="mb-4 opacity-20" />
          <p>
            {#if search}
              {$t('management.podcasts.noMatch', { search })}
            {:else if stateFilter === UNKNOWN}
              {$t('management.podcasts.queueEmpty')}
            {:else}
              {$t('management.podcasts.listEmpty')}
            {/if}
          </p>
        </div>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="bg-white/5 text-spotify-lightgray text-[10px] uppercase tracking-wider">
                <th class="p-4">{$t('management.podcasts.show')}</th>
                <th class="p-4">{$t('management.podcasts.episodes')}</th>
                <th class="p-4">{$t('management.genres.outcome')}</th>
                <th class="p-4">{$t('management.genres.decision')}</th>
                <th class="p-4 text-right">{$t('management.genres.actions')}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-spotify-gray divide-opacity-30">
              {#each visibleRows as row (row.id)}
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="p-4">
                    <div class="font-bold">{row.name}</div>
                    {#if extraAliases(row).length}
                      <div class="text-xs text-spotify-lightgray mt-0.5">
                        {$t('management.podcasts.alsoSpelled', { aliases: extraAliases(row).join(' · ') })}
                      </div>
                    {/if}
                    {#if row.state !== UNKNOWN}
                      <span
                        class="text-[10px] font-bold uppercase px-2 py-0.5 rounded {row.state === WHITE ? 'bg-spotify-green/20 text-spotify-green' : 'bg-red-500/10 text-red-500'}"
                      >
                        {row.state === WHITE ? $t('management.podcasts.approved') : $t('management.podcasts.rejected')}
                      </span>
                    {/if}
                  </td>
                  <td class="p-4 text-spotify-lightgray">{describeEpisodes(row)}</td>
                  <td class="p-4 text-spotify-lightgray">{describeOutcome(row)}</td>
                  <td class="p-4 text-spotify-lightgray text-xs">{describeDecision(row)}</td>
                  <td class="p-4 text-right">
                    <div class="flex justify-end gap-2">
                      {#if row.state !== WHITE}
                        <button
                          onclick={() => decide(row, WHITE)}
                          class="bg-spotify-green text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <Check size={14} /> {$t('management.genres.approve')}
                        </button>
                      {/if}
                      {#if row.state !== BLACK}
                        <button
                          onclick={() => decide(row, BLACK)}
                          class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <X size={14} /> {$t('management.genres.reject')}
                        </button>
                      {/if}
                      <button
                        onclick={() => openDecision(row)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                      >
                        <Merge size={14} /> {$t('management.podcasts.merge')}
                      </button>
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  </div>
</section>

{#if deciding}
  <div class="fixed inset-0 bg-black/80 flex items-center justify-center z-[1100] animate-in fade-in duration-200">
    <div class="bg-[#282828] p-8 rounded-xl border border-white border-opacity-10 max-w-md w-full shadow-2xl">
      <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">
        <Podcast class="text-spotify-green" /> {deciding.name}
      </h3>
      <p class="text-spotify-lightgray mb-6">
        {$t('management.podcasts.decisionHelp')}
      </p>

      <div class="mb-6">
        <span class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">{$t('management.health.status')}</span>
        <div class="flex gap-2">
          <button
            class="flex-1 py-2 rounded-full font-bold text-sm transition-all {decisionState === WHITE ? 'bg-spotify-green text-black' : 'bg-white/10 text-white hover:bg-white/20'}"
            onclick={() => (decisionState = WHITE)}
          >
            {$t('management.genres.approve')}
          </button>
          <button
            class="flex-1 py-2 rounded-full font-bold text-sm transition-all {decisionState === BLACK ? 'bg-red-600 text-white' : 'bg-white/10 text-white hover:bg-white/20'}"
            onclick={() => (decisionState = BLACK)}
          >
            {$t('management.genres.reject')}
          </button>
        </div>
      </div>

      <div class="mb-6">
        <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1" for="podcast-merge-target">
          {$t('management.podcasts.mergeInto')}
        </label>
        <p class="text-xs text-spotify-lightgray mb-2">{$t('management.podcasts.mergeHelp')}</p>
        <select
          id="podcast-merge-target"
          bind:value={decisionMergeId}
          class="w-full bg-spotify-dark border border-spotify-gray rounded-md px-3 py-2 text-sm focus:outline-none focus:border-spotify-green"
        >
          <option value="">{$t('management.podcasts.noMerge')}</option>
          {#each targets as target (target.id)}
            <option value={String(target.id)}>{target.name}</option>
          {/each}
        </select>
      </div>

      {#if !decisionMergeId}
        <div class="mb-6 grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1" for="podcast-host">
              {$t('management.podcasts.host')}
            </label>
            <input
              id="podcast-host"
              type="text"
              bind:value={decisionHost}
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md px-3 py-2 text-sm focus:outline-none focus:border-spotify-green"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1" for="podcast-station">
              {$t('management.podcasts.station')}
            </label>
            <input
              id="podcast-station"
              type="text"
              bind:value={decisionStation}
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md px-3 py-2 text-sm focus:outline-none focus:border-spotify-green"
            />
          </div>
        </div>
      {/if}

      {#if pendingDecision.error}
        <p class="text-sm text-red-500 mb-4">{pendingDecision.error}</p>
      {/if}

      <div class="flex gap-4">
        <button
          class="flex-1 py-3 rounded-full font-bold bg-spotify-green text-black hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100"
          disabled={!pendingDecision.valid}
          onclick={() => decide(deciding, decisionState, { mergeIntoId: decisionMergeId, host: decisionHost, station: decisionStation })}
        >
          {$t('common.save')}
        </button>
        <button
          class="flex-1 py-3 rounded-full font-bold bg-white/10 text-white hover:bg-white/20 transition-all"
          onclick={() => (deciding = null)}
        >
          {$t('common.cancel')}
        </button>
      </div>
    </div>
  </div>
{/if}
