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
    HelpCircle,
    Pencil,
    Plus,
    Trash2
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
    buildRename,
    buildAlias,
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

  // The row being renamed / respelled, kept apart from `deciding`: naming a show
  // and deciding on it are separate jobs, and the name usually has to be fixed
  // before the decision means anything.
  let editing = $state(null);
  let editName = $state('');
  let newAlias = $state('');

  const visibleRows = $derived(filterPodcasts(rows, search));
  const counts = $derived(summarize(rows));
  const targets = $derived(mergeTargets(whiteShows, deciding?.id));
  const pendingRename = $derived(editing ? buildRename(editName) : { valid: false, error: null });
  const pendingAlias = $derived(newAlias.trim() ? buildAlias(newAlias) : { valid: false, error: null });
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

  function openEdit(rowToEdit) {
    editing = rowToEdit;
    editName = rowToEdit.name;
    newAlias = '';
  }

  /**
   * Re-reads the table and re-points the open modal at the fresh row, so the
   * spellings in front of the curator are the ones the server now holds.
   */
  async function reloadEditing() {
    await Promise.all([fetchPodcasts(), fetchWhiteShows()]);
    if (editing) editing = rows.find((row) => row.id === editing.id) ?? editing;
  }

  /**
   * One request from the edit modal, with the reply turned into a message.
   *
   * @returns {Promise<boolean>} whether the server accepted it
   */
  async function submitEdit(url, init, message) {
    try {
      const res = await fetch(url, {
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        ...init
      });
      if (!res.ok) {
        const data = await res.json();
        onError(data.detail || $t('management.podcasts.saveFailed'));
        return false;
      }
      onMessage(message);
      await reloadEditing();
      return true;
    } catch (err) {
      onError($t('management.podcasts.saveNetworkError'));
      return false;
    }
  }

  async function saveName() {
    const rename = buildRename(editName);
    if (!rename.valid) {
      onError(rename.error);
      return;
    }
    await submitEdit(
      `${API_BASE}/api/rules/podcasts/${editing.id}/rename`,
      { method: 'POST', body: JSON.stringify(rename.payload) },
      $t('management.podcasts.renamed', { name: rename.payload.name })
    );
  }

  async function addAlias() {
    const spelling = buildAlias(newAlias);
    if (!spelling.valid) {
      onError(spelling.error);
      return;
    }
    const added = await submitEdit(
      `${API_BASE}/api/rules/podcasts/${editing.id}/aliases`,
      { method: 'POST', body: JSON.stringify(spelling.payload) },
      $t('management.podcasts.spellingAdded', { alias: spelling.payload.alias })
    );
    if (added) newAlias = '';
  }

  async function removeAlias(alias) {
    await submitEdit(
      `${API_BASE}/api/rules/podcasts/${editing.id}/aliases?alias=${encodeURIComponent(alias)}`,
      { method: 'DELETE' },
      $t('management.podcasts.spellingRemoved', { alias })
    );
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
        <Podcast class="text-brand" size={32} /> {$t('management.tabs.podcastCuration')}
      </h2>
      <p class="text-muma-spotify-text">
        {$t('management.podcasts.subtitle')}
      </p>
    </div>

    <div class="flex bg-muma-spotify-panel p-1 rounded-full border border-white/5">
      {#each STATE_FILTERS as filter (filter.id)}
        <button
          class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {stateFilter === filter.id ? 'bg-white text-black' : 'text-muma-spotify-text hover:text-white'}"
          onclick={() => (stateFilter = filter.id)}
        >
          {filter.label}
        </button>
      {/each}
    </div>
  </header>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
      <h3 class="text-xl font-bold flex items-center gap-2">
        {#if stateFilter === UNKNOWN}<HelpCircle size={20} class="text-yellow-500" />{/if}
        {#if stateFilter === WHITE}<CircleCheck size={20} class="text-brand" />{/if}
        {#if stateFilter === BLACK}<CircleSlash size={20} class="text-red-500" />{/if}
        {STATE_FILTERS.find((f) => f.id === stateFilter)?.label}
        <span class="text-muma-spotify-text text-sm font-normal">({counts.total})</span>
      </h3>

      <div class="flex items-center gap-3">
        <div class="relative">
          <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" />
          <input
            type="text"
            bind:value={search}
            placeholder={$t('management.podcasts.searchPlaceholder')}
            aria-label={$t('management.podcasts.searchLabel')}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-brand transition-colors"
          />
        </div>
        <button
          onclick={fetchPodcasts}
          disabled={loading}
          aria-label={$t('common.refresh')}
          class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
        </button>
      </div>
    </div>

    <div class="min-h-[200px]">
      {#if loading && rows.length === 0}
        <div class="flex items-center justify-center p-20">
          <RefreshCw class="animate-spin text-brand" size={32} />
        </div>
      {:else if visibleRows.length === 0}
        <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
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
              <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
                <th class="p-4">{$t('management.podcasts.show')}</th>
                <th class="p-4">{$t('management.podcasts.episodes')}</th>
                <th class="p-4">{$t('management.genres.outcome')}</th>
                <th class="p-4">{$t('management.genres.decision')}</th>
                <th class="p-4 text-right">{$t('management.genres.actions')}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each visibleRows as row (row.id)}
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="p-4">
                    <div class="font-bold">{row.name}</div>
                    {#if extraAliases(row).length}
                      <div class="text-xs text-muma-spotify-text mt-0.5">
                        {$t('management.podcasts.alsoSpelled', { aliases: extraAliases(row).join(' · ') })}
                      </div>
                    {/if}
                    {#if row.state !== UNKNOWN}
                      <span
                        class="text-[10px] font-bold uppercase px-2 py-0.5 rounded {row.state === WHITE ? 'bg-brand/20 text-brand' : 'bg-red-500/10 text-red-500'}"
                      >
                        {row.state === WHITE ? $t('management.podcasts.approved') : $t('management.podcasts.rejected')}
                      </span>
                    {/if}
                  </td>
                  <td class="p-4 text-muma-spotify-text">{describeEpisodes(row)}</td>
                  <td class="p-4 text-muma-spotify-text">{describeOutcome(row)}</td>
                  <td class="p-4 text-muma-spotify-text text-xs">{describeDecision(row)}</td>
                  <td class="p-4 text-right">
                    <div class="flex justify-end gap-2">
                      {#if row.state !== WHITE}
                        <button
                          onclick={() => decide(row, WHITE)}
                          class="bg-brand text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
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
                        onclick={() => openEdit(row)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                      >
                        <Pencil size={14} /> {$t('management.podcasts.edit')}
                      </button>
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

{#if editing}
  <div class="fixed inset-0 bg-black/80 flex items-center justify-center z-[1100] animate-in fade-in duration-200">
    <div class="bg-[#282828] p-8 rounded-xl border border-white/10 max-w-lg w-full shadow-2xl">
      <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">
        <Pencil class="text-brand" /> {editing.name}
      </h3>

      <div class="mb-6">
        <label class="block text-xs font-bold text-muma-spotify-text uppercase mb-1" for="podcast-name">
          {$t('management.podcasts.name')}
        </label>
        <p class="text-xs text-muma-spotify-text mb-2">{$t('management.podcasts.nameHelp')}</p>
        <div class="flex gap-2">
          <input
            id="podcast-name"
            type="text"
            bind:value={editName}
            class="flex-1 bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
          />
          <button
            class="bg-brand text-black px-4 rounded-md font-bold text-sm hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
            disabled={!pendingRename.valid}
            onclick={saveName}
          >
            {$t('common.save')}
          </button>
        </div>
        {#if pendingRename.error}
          <p class="text-sm text-red-500 mt-2">{pendingRename.error}</p>
        {/if}
      </div>

      <div class="mb-6">
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">
          {$t('management.podcasts.spellings')}
        </span>
        <p class="text-xs text-muma-spotify-text mb-2">{$t('management.podcasts.spellingsHelp')}</p>
        {#if (editing.aliases || []).length}
          <ul class="space-y-1 mb-3 max-h-40 overflow-y-auto">
            {#each editing.aliases as alias (alias)}
              <li class="flex items-center justify-between gap-2 bg-black/20 rounded px-3 py-1.5 text-sm">
                <span class="truncate">{alias}</span>
                <button
                  onclick={() => removeAlias(alias)}
                  aria-label={$t('management.podcasts.removeSpelling', { alias })}
                  class="text-muma-spotify-text hover:text-red-500 transition-colors shrink-0"
                >
                  <Trash2 size={14} />
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="text-sm text-muma-spotify-text mb-3">{$t('management.podcasts.noSpellings')}</p>
        {/if}
        <div class="flex gap-2">
          <input
            type="text"
            bind:value={newAlias}
            placeholder={$t('management.podcasts.spellingPlaceholder')}
            aria-label={$t('management.podcasts.addSpelling')}
            class="flex-1 bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
          />
          <button
            class="bg-white/10 text-white px-4 rounded-md font-bold text-sm hover:bg-white/20 transition-colors disabled:opacity-50 flex items-center gap-1"
            disabled={!pendingAlias.valid}
            onclick={addAlias}
          >
            <Plus size={14} /> {$t('management.podcasts.addSpelling')}
          </button>
        </div>
        {#if pendingAlias.error}
          <p class="text-sm text-red-500 mt-2">{pendingAlias.error}</p>
        {/if}
      </div>

      <button
        class="w-full py-3 rounded-full font-bold bg-white/10 text-white hover:bg-white/20 transition-all"
        onclick={() => (editing = null)}
      >
        {$t('common.close')}
      </button>
    </div>
  </div>
{/if}

{#if deciding}
  <div class="fixed inset-0 bg-black/80 flex items-center justify-center z-[1100] animate-in fade-in duration-200">
    <div class="bg-[#282828] p-8 rounded-xl border border-white/10 max-w-md w-full shadow-2xl">
      <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">
        <Podcast class="text-brand" /> {deciding.name}
      </h3>
      <p class="text-muma-spotify-text mb-6">
        {$t('management.podcasts.decisionHelp')}
      </p>

      <div class="mb-6">
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">{$t('management.health.status')}</span>
        <div class="flex gap-2">
          <button
            class="flex-1 py-2 rounded-full font-bold text-sm transition-all {decisionState === WHITE ? 'bg-brand text-black' : 'bg-white/10 text-white hover:bg-white/20'}"
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
        <label class="block text-xs font-bold text-muma-spotify-text uppercase mb-1" for="podcast-merge-target">
          {$t('management.podcasts.mergeInto')}
        </label>
        <p class="text-xs text-muma-spotify-text mb-2">{$t('management.podcasts.mergeHelp')}</p>
        <select
          id="podcast-merge-target"
          bind:value={decisionMergeId}
          class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
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
            <label class="block text-xs font-bold text-muma-spotify-text uppercase mb-1" for="podcast-host">
              {$t('management.podcasts.host')}
            </label>
            <input
              id="podcast-host"
              type="text"
              bind:value={decisionHost}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-muma-spotify-text uppercase mb-1" for="podcast-station">
              {$t('management.podcasts.station')}
            </label>
            <input
              id="podcast-station"
              type="text"
              bind:value={decisionStation}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
            />
          </div>
        </div>
      {/if}

      {#if pendingDecision.error}
        <p class="text-sm text-red-500 mb-4">{pendingDecision.error}</p>
      {/if}

      <div class="flex gap-4">
        <button
          class="flex-1 py-3 rounded-full font-bold bg-brand text-black hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100"
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
