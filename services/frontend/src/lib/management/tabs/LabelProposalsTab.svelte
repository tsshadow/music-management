<script>
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { RefreshCw, Check, X, Tags, FolderX } from '@lucide/svelte';
  import { describeImportConflict, groupByLabel } from '../labelProposals.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let proposals = $state([]);
  /** Folder pairs (bug 091) and single files (bug 119) the importer left in place for a human. */
  let conflicts = $state([]);
  let chosen = $state({});
  let labelOptions = $state([]);
  let loading = $state(false);
  let busy = $state(false);

  const groups = $derived(groupByLabel(proposals));

  /** The key a group's chosen label is stored under; null labels need a stable string. */
  function keyOf(group) {
    return group.label ?? '';
  }

  function labelFor(group) {
    return chosen[keyOf(group)] ?? group.label ?? '';
  }

  async function load() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/label-proposals?status=new`, { headers: getHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      proposals = await res.json();
    } catch (e) {
      onError(e.message);
    } finally {
      loading = false;
    }
    await loadConflicts();
  }

  /**
   * The standing folder conflicts. Read-only and secondary to the proposals, so a failure
   * here leaves the list empty instead of reporting an error over the proposals.
   */
  async function loadConflicts() {
    try {
      const res = await fetch(`${API_BASE}/api/import-conflicts`, { headers: getHeaders() });
      conflicts = res.ok ? await res.json() : [];
    } catch {
      conflicts = [];
    }
  }

  /**
   * Only labels the library already knows, so a different spelling cannot quietly
   * create a second folder beside the one that exists.
   */
  async function searchLabels(query) {
    if (!query) {
      labelOptions = [];
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/labels?q=${encodeURIComponent(query)}`, { headers: getHeaders() });
      labelOptions = res.ok ? await res.json() : [];
    } catch {
      labelOptions = [];
    }
  }

  async function confirmGroup(group) {
    const label = labelFor(group);
    if (!label || busy) return;
    busy = true;
    let confirmed = 0;
    let stale = 0;
    let conflict = 0;
    try {
      for (const proposal of group.proposals) {
        const res = await fetch(`${API_BASE}/api/label-proposals/${proposal.id}/confirm`, {
          method: 'POST',
          headers: { ...getHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ label })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = await res.json();
        if (body.status === 'stale') stale += 1;
        // The destination folder already holds a release, so nothing moved and the
        // proposal is still open. Counting it as confirmed would report a move that
        // did not happen.
        else if (body.status === 'conflict' || body.status === 'duplicate') conflict += 1;
        else confirmed += 1;
      }
      onMessage($t('management.labelProposals.confirmed', { count: confirmed, label, stale, conflict }));
      await load();
    } catch (e) {
      onError(e.message);
    } finally {
      busy = false;
    }
  }

  async function reject(proposal) {
    if (busy) return;
    busy = true;
    try {
      const res = await fetch(`${API_BASE}/api/label-proposals/${proposal.id}/reject`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      onMessage($t('management.labelProposals.rejected'));
      await load();
    } catch (e) {
      onError(e.message);
    } finally {
      busy = false;
    }
  }

  onMount(load);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <Tags class="text-brand" size={32} /> {$t('management.tabs.labelProposals')}
      </h2>
      <p class="text-muma-spotify-text max-w-3xl">
        {$t('management.labelProposals.description')}
      </p>
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

  {#if loading && proposals.length === 0}
    <div class="flex items-center justify-center p-20">
      <RefreshCw class="animate-spin text-brand" size={32} />
    </div>
  {:else if groups.length === 0}
    <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
      <Tags size={48} class="mb-4 opacity-20" />
      <p>{$t('management.labelProposals.empty')}</p>
    </div>
  {:else}
    <div class="space-y-6">
      {#each groups as group (keyOf(group))}
        <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
          <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
            <h3 class="text-xl font-bold flex items-center gap-2">
              {#if group.label}
                {group.label}
              {:else}
                <span class="text-muma-spotify-text italic font-normal">
                  {$t('management.labelProposals.noLabel')}
                </span>
              {/if}
              <span class="text-muma-spotify-text text-sm font-normal tabular-nums">({group.proposals.length})</span>
            </h3>

            <div class="flex items-center gap-3">
              <input
                type="text"
                list="label-proposal-options"
                placeholder={$t('management.labelProposals.label')}
                aria-label={$t('management.labelProposals.label')}
                value={labelFor(group)}
                oninput={(e) => {
                  chosen[keyOf(group)] = e.currentTarget.value;
                  searchLabels(e.currentTarget.value);
                }}
                class="w-56 bg-muma-spotify-dark border border-muma-spotify-panel rounded-full px-4 py-2 text-sm focus:outline-none focus:border-brand transition-colors"
              />
              <button
                onclick={() => confirmGroup(group)}
                disabled={busy || !labelFor(group)}
                class="bg-brand text-black px-4 py-2 rounded-full font-bold text-xs transition-transform hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 flex items-center gap-1 shrink-0"
              >
                <Check size={14} /> {$t('management.labelProposals.confirmGroup')}
              </button>
            </div>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
              <thead>
                <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
                  <th class="p-4">{$t('management.labelProposals.release')}</th>
                  <th class="p-4">{$t('management.labelProposals.catId')}</th>
                  <th class="p-4">{$t('management.labelProposals.source')}</th>
                  <th class="p-4 text-right">{$t('management.labelProposals.actions')}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-muma-spotify-panel/30">
                {#each group.proposals as proposal (proposal.id)}
                  <tr class="hover:bg-white/5 transition-colors">
                    <td class="p-4 font-medium break-all">{proposal.folder}</td>
                    <td class="p-4 text-muma-spotify-text text-xs">
                      {#if proposal.catid}
                        <span class="font-mono">{proposal.catid}</span>
                      {:else}
                        <span class="italic opacity-70">{$t('management.labelProposals.noCatId')}</span>
                      {/if}
                    </td>
                    <td class="p-4 text-muma-spotify-text text-xs whitespace-nowrap">
                      {proposal.source}
                      <span class="tabular-nums opacity-70">({proposal.confidence})</span>
                    </td>
                    <td class="p-4 text-right">
                      <button
                        onclick={() => reject(proposal)}
                        disabled={busy}
                        class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 inline-flex items-center gap-1"
                      >
                        <X size={14} /> {$t('management.labelProposals.reject')}
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/each}
    </div>

    <datalist id="label-proposal-options">
      {#each labelOptions as option (option.id)}
        <option value={option.name}></option>
      {/each}
    </datalist>
  {/if}
  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20">
      <h3 class="text-xl font-bold flex items-center gap-2">
        <FolderX class="text-brand" size={20} /> {$t('management.labelProposals.conflicts')}
        <span class="text-muma-spotify-text text-sm font-normal tabular-nums">({conflicts.length})</span>
      </h3>
      <p class="text-muma-spotify-text text-sm mt-2 max-w-3xl">
        {$t('management.labelProposals.conflictsDescription')}
      </p>
    </div>
    {#if conflicts.length === 0}
      <p class="p-6 text-muma-spotify-text text-sm">{$t('management.labelProposals.conflictsEmpty')}</p>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
              <th class="p-4">{$t('management.labelProposals.conflictProblem')}</th>
              <th class="p-4">{$t('management.labelProposals.conflictSource')}</th>
              <th class="p-4">{$t('management.labelProposals.conflictStep')}</th>
              <th class="p-4">{$t('management.labelProposals.conflictSince')}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30">
            {#each conflicts as conflict (conflict.step + conflict.source + conflict.target)}
              {@const problem = describeImportConflict(conflict)}
              <tr class="hover:bg-white/5 transition-colors">
                <td class="p-4 break-all">
                  <span class="font-medium">{$t(`management.labelProposals.${problem.key}`)}</span>
                  {#if problem.detail}
                    <span class="block text-muma-spotify-text text-xs mt-1">{problem.detail}</span>
                  {/if}
                </td>
                <td class="p-4 break-all">{conflict.source}</td>
                <td class="p-4 text-muma-spotify-text text-xs">{conflict.step}</td>
                <td class="p-4 text-muma-spotify-text text-xs whitespace-nowrap tabular-nums">{conflict.first_seen}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </div>
</section>
