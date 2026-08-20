<script>
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { RefreshCw, Check, X } from '@lucide/svelte';
  import { groupByLabel } from '../labelProposals.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let proposals = $state([]);
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
        else confirmed += 1;
      }
      onMessage($t('management.labelProposals.confirmed', { count: confirmed, label, stale }));
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

<div class="tab-panel">
  <header class="panel-header">
    <p class="hint">{$t('management.labelProposals.description')}</p>
    <button class="btn" onclick={load} disabled={loading}>
      <RefreshCw size={16} /> {$t('common.refresh')}
    </button>
  </header>

  {#if loading}
    <p class="hint">{$t('common.loading')}</p>
  {:else if groups.length === 0}
    <p class="hint">{$t('management.labelProposals.empty')}</p>
  {:else}
    {#each groups as group (keyOf(group))}
      <section class="group">
        <div class="group-header">
          <h3>{group.label ?? $t('management.labelProposals.noLabel')}</h3>
          <span class="count">{group.proposals.length}</span>
          <input
            type="text"
            list="label-proposal-options"
            placeholder={$t('management.labelProposals.label')}
            value={labelFor(group)}
            oninput={(e) => {
              chosen[keyOf(group)] = e.currentTarget.value;
              searchLabels(e.currentTarget.value);
            }} />
          <button class="btn" onclick={() => confirmGroup(group)} disabled={busy || !labelFor(group)}>
            <Check size={16} /> {$t('management.labelProposals.confirmGroup')}
          </button>
        </div>
        <ul class="releases">
          {#each group.proposals as proposal (proposal.id)}
            <li>
              <span class="folder">{proposal.folder}</span>
              <span class="catid">{proposal.catid ?? $t('management.labelProposals.noCatId')}</span>
              <span class="source">{proposal.source} ({proposal.confidence})</span>
              <button class="btn ghost" onclick={() => reject(proposal)} disabled={busy}>
                <X size={16} /> {$t('management.labelProposals.reject')}
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/each}
    <datalist id="label-proposal-options">
      {#each labelOptions as option (option.id)}
        <option value={option.name}></option>
      {/each}
    </datalist>
  {/if}
</div>

<style>
  .group {
    margin-bottom: 1.5rem;
  }
  .group-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-wrap: wrap;
  }
  .group-header h3 {
    margin: 0;
  }
  .count {
    opacity: 0.7;
    font-variant-numeric: tabular-nums;
  }
  .releases {
    list-style: none;
    margin: 0.5rem 0 0;
    padding: 0;
  }
  .releases li {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.25rem 0;
    flex-wrap: wrap;
  }
  .folder {
    flex: 1 1 20rem;
    word-break: break-word;
  }
  .catid,
  .source {
    opacity: 0.7;
    font-size: 0.85em;
  }
</style>
