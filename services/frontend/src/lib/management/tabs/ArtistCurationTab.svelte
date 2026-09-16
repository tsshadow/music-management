<script>
  import { t } from '../../i18n/index.js';
  import { onDestroy, onMount } from 'svelte';
  import { SvelteURLSearchParams } from 'svelte/reactivity';
  import {
    RefreshCw,
    Search,
    Check,
    X,
    Replace,
    Undo2,
    Users,
    Sparkles,
    ChevronLeft,
    ChevronRight,
    CircleSlash,
    CircleCheck,
    HelpCircle
  } from '@lucide/svelte';
  import {
    WHITE,
    BLACK,
    UNKNOWN,
    STATE_FILTERS,
    PROPOSAL_FILTERS,
    PAGE_SIZE,
    describeOutcome,
    describeProposal,
    describeDecision,
    buildDecision,
    planFromProposals,
    pageOf
  } from '../artistCuration.js';

  /**
   * Which names in the library are artists at all -- the genre curation tab's model
   * over `library_artists`. The queue is worked in classes: the proposal filter narrows
   * it to what the last analysis suggested (everything that reads as noise, every
   * spelling variant of an approved name), a page of those is selected at once, and
   * "apply proposals" turns the page into decisions. Nothing is ever decided by the
   * analysis itself; the button is the decision.
   */
  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let rows = $state([]);
  let total = $state(0);
  let offset = $state(0);
  let loading = $state(false);
  let stateFilter = $state(UNKNOWN);
  let proposalFilter = $state(null);
  let search = $state('');
  let summary = $state(null);
  let selected = $state([]);

  // The analysis job, while one runs. Polled rather than streamed: a run is seconds to
  // a minute, and the jobs websocket is more plumbing than that is worth.
  let analysisJob = $state(null);
  let pollTimer = null;

  // The row being corrected in the modal, and the target being typed for it.
  let correcting = $state(null);
  let correctionTarget = $state('');

  const paging = $derived(pageOf(total, offset));
  /** A count for display; a summary from an older server may lack a field, which is 0 here. */
  const n = (value) => Number(value ?? 0).toLocaleString('nl-NL');
  const allVisibleSelected = $derived(rows.length > 0 && rows.every((row) => selected.includes(row.name)));
  const selectedRows = $derived(rows.filter((row) => selected.includes(row.name)));
  const plan = $derived(planFromProposals(selectedRows));
  const pendingCorrection = $derived(
    correcting
      ? buildDecision({ names: [correcting.name], state: BLACK, canonicalName: correctionTarget })
      : { valid: false, error: null }
  );

  // A search that changes the query should land on the first page again; typing
  // waits a moment so every keystroke is not a request.
  let searchTimer = null;
  function onSearchInput(event) {
    search = event.currentTarget.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      offset = 0;
      fetchRows();
    }, 250);
  }

  function setStateFilter(id) {
    stateFilter = id;
    offset = 0;
    selected = [];
    fetchRows();
  }

  function setProposalFilter(id) {
    proposalFilter = id;
    offset = 0;
    selected = [];
    fetchRows();
  }

  function turnPage(delta) {
    const next = offset + delta * PAGE_SIZE;
    if (next < 0 || next >= total) return;
    offset = next;
    selected = [];
    fetchRows();
  }

  async function fetchRows() {
    loading = true;
    try {
      const params = new SvelteURLSearchParams({ state: stateFilter, limit: String(PAGE_SIZE), offset: String(offset) });
      if (search.trim()) params.set('q', search.trim());
      if (proposalFilter) params.set('proposal', proposalFilter);
      const res = await fetch(`${API_BASE}/api/rules/artists?${params}`, { headers: getHeaders() });
      if (res.ok) {
        const body = await res.json();
        rows = body.rows || [];
        total = body.total || 0;
      } else {
        onError($t('management.artists.loadFailed'));
      }
    } catch {
      onError($t('management.artists.loadNetworkError'));
    } finally {
      loading = false;
    }
  }

  async function fetchSummary() {
    try {
      const res = await fetch(`${API_BASE}/api/rules/artists/summary`, { headers: getHeaders() });
      if (res.ok) {
        const body = await res.json();
        summary = body && typeof body === 'object' && !Array.isArray(body) ? body : null;
      }
    } catch (err) {
      console.error('Kon samenvatting artiestcuratie niet ophalen:', err);
    }
  }

  async function refresh() {
    await Promise.all([fetchRows(), fetchSummary()]);
  }

  /**
   * One decide call. Reports in words what happened, then reloads: the row moves
   * out of the queue, and the summary counts move with it.
   */
  async function submit(decision, describe) {
    if (!decision.valid) {
      onError($t(decision.error));
      return false;
    }
    try {
      const res = await fetch(`${API_BASE}/api/rules/artists/decide`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(decision.payload)
      });
      if (res.ok) {
        if (describe) onMessage(describe);
        return true;
      }
      const data = await res.json().catch(() => ({}));
      onError(data.detail || $t('management.artists.saveFailed'));
    } catch {
      onError($t('management.artists.saveNetworkError'));
    }
    return false;
  }

  async function decideOne(row, state) {
    const ok = await submit(
      buildDecision({ names: [row.name], state }),
      $t(state === WHITE ? 'management.artists.approved' : 'management.artists.rejected', { name: row.name })
    );
    if (ok) {
      selected = selected.filter((name) => name !== row.name);
      await refresh();
    }
  }

  async function decideSelected(state) {
    const names = [...selected];
    const ok = await submit(
      buildDecision({ names, state }),
      $t(state === WHITE ? 'management.artists.approvedMany' : 'management.artists.rejectedMany', {
        count: names.length
      })
    );
    if (ok) {
      selected = [];
      await refresh();
    }
  }

  /** Every selected row's proposal, as decisions -- the bulk step of a class of names. */
  async function applySelectedProposals() {
    let applied = 0;
    for (const decision of plan.decisions) {
      const ok = await submit(buildDecision({ names: decision.names, state: decision.state, canonicalName: decision.canonical_name || '' }));
      if (!ok) break;
      applied += decision.names.length;
    }
    if (applied) {
      onMessage($t('management.artists.appliedProposals', { count: applied, skipped: plan.skipped.length }));
    } else if (plan.skipped.length) {
      onError($t('management.artists.nothingToApply'));
    }
    selected = [];
    await refresh();
  }

  async function saveCorrection() {
    const target = correctionTarget.trim();
    const ok = await submit(
      pendingCorrection,
      $t('management.artists.corrected', { name: correcting.name, target })
    );
    if (ok) {
      selected = selected.filter((name) => name !== correcting.name);
      correcting = null;
      await refresh();
    }
  }

  async function undo(row) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/artists/${encodeURIComponent(row.name)}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.artists.undone', { name: row.name }));
        await refresh();
      } else {
        const data = await res.json().catch(() => ({}));
        onError(data.detail || $t('management.artists.saveFailed'));
      }
    } catch {
      onError($t('management.artists.saveNetworkError'));
    }
  }

  function openCorrection(row) {
    correcting = row;
    correctionTarget = row.canonical_name || row.proposal_target || '';
  }

  function toggleSelected(name) {
    selected = selected.includes(name) ? selected.filter((existing) => existing !== name) : [...selected, name];
  }

  function toggleAllVisible() {
    selected = allVisibleSelected ? [] : rows.map((row) => row.name);
  }

  async function startAnalysis() {
    try {
      const res = await fetch(`${API_BASE}/api/rules/artists/analyze`, { method: 'POST', headers: getHeaders() });
      if (!res.ok) {
        onError($t('management.artists.analysisFailed'));
        return;
      }
      const body = await res.json();
      analysisJob = { id: body.job_id, status: body.status };
      pollAnalysis();
    } catch {
      onError($t('management.artists.saveNetworkError'));
    }
  }

  async function pollAnalysis() {
    if (!analysisJob) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/artists/analyze/${analysisJob.id}`, { headers: getHeaders() });
      if (res.ok) {
        const status = await res.json();
        analysisJob = { ...analysisJob, ...status };
        if (status.status === 'finished') {
          onMessage($t('management.artists.analysisDone', { count: status.total ?? 0 }));
          analysisJob = null;
          await refresh();
          return;
        }
        if (status.status === 'failed') {
          onError(status.error || $t('management.artists.analysisFailed'));
          analysisJob = null;
          return;
        }
      }
    } catch (err) {
      console.error('Kon analyse-status niet ophalen:', err);
    }
    pollTimer = setTimeout(pollAnalysis, 2000);
  }

  // The first visit has no advice to show, so the analysis starts on its own; after
  // that it is the button, because a run rewrites every proposal and a curator
  // halfway through a class of names would lose their place.
  onMount(async () => {
    await refresh();
    if (summary && !summary.analyzed_at && !analysisJob) await startAnalysis();
  });
  onDestroy(() => {
    clearTimeout(pollTimer);
    clearTimeout(searchTimer);
  });
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500" data-testid="artist-curation">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <Users class="text-brand" size={32} /> {$t('management.tabs.artistCuration')}
      </h2>
      <p class="text-muma-spotify-text">{$t('management.artists.subtitle')}</p>
    </div>

    <div class="flex bg-muma-spotify-panel p-1 rounded-full border border-white/5">
      {#each STATE_FILTERS as filter (filter.id)}
        <button
          class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {stateFilter === filter.id ? 'bg-white text-black' : 'text-muma-spotify-text hover:text-white'}"
          onclick={() => setStateFilter(filter.id)}
        >
          {$t(filter.labelKey)}
        </button>
      {/each}
    </div>
  </header>

  {#if summary}
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="artist-summary">
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">{$t('management.artists.filterUnknown')}</p>
        <p class="text-2xl font-extrabold m-0">{n(summary.unknown)}</p>
        <p class="text-xs text-muma-spotify-text m-0">{$t('management.artists.ofInLibrary', { count: n(summary.in_library) })}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">{$t('management.artists.filterWhite')}</p>
        <p class="text-2xl font-extrabold m-0 text-brand">{n(summary.white)}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">{$t('management.artists.filterBlack')}</p>
        <p class="text-2xl font-extrabold m-0 text-red-400">{n(summary.black)}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4 flex flex-col gap-2">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">{$t('management.artists.proposals')}</p>
        <p class="text-sm m-0">
          {$t('management.artists.proposalCounts', {
            reject: n(summary.proposals?.reject),
            rewrite: n((summary.proposals?.rewrite ?? 0) + (summary.proposals?.split ?? 0))
          })}
        </p>
        <button
          class="self-start bg-white/10 hover:bg-white/20 text-white px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 disabled:opacity-50"
          disabled={Boolean(analysisJob)}
          onclick={startAnalysis}
        >
          <Sparkles size={14} />
          {analysisJob ? $t('management.artists.analysing') : $t('management.artists.analyse')}
        </button>
        <p class="text-[11px] text-muma-spotify-text m-0">
          {summary.analyzed_at ? $t('management.artists.analysedAt', { when: summary.analyzed_at }) : $t('management.artists.neverAnalysed')}
        </p>
      </div>
    </div>
  {/if}

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
      <h3 class="text-xl font-bold flex items-center gap-2">
        {#if stateFilter === UNKNOWN}<HelpCircle size={20} class="text-yellow-500" />{/if}
        {#if stateFilter === WHITE}<CircleCheck size={20} class="text-brand" />{/if}
        {#if stateFilter === BLACK}<CircleSlash size={20} class="text-red-500" />{/if}
        {$t(STATE_FILTERS.find((f) => f.id === stateFilter)?.labelKey)}
        <span class="text-muma-spotify-text text-sm font-normal">({n(total)})</span>
      </h3>

      <div class="flex items-center gap-3 flex-wrap">
        {#if stateFilter === UNKNOWN}
          <div class="flex bg-muma-spotify-dark p-1 rounded-full border border-white/5" role="group" aria-label={$t('management.artists.proposals')}>
            {#each PROPOSAL_FILTERS as filter (filter.id ?? 'any')}
              <button
                class="px-3 py-1 rounded-full text-xs font-bold transition-colors {proposalFilter === filter.id ? 'bg-white text-black' : 'text-muma-spotify-text hover:text-white'}"
                aria-pressed={proposalFilter === filter.id}
                onclick={() => setProposalFilter(filter.id)}
              >
                {$t(filter.labelKey)}
              </button>
            {/each}
          </div>
        {/if}
        <div class="relative">
          <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" />
          <input
            type="text"
            value={search}
            oninput={onSearchInput}
            placeholder={$t('management.artists.searchPlaceholder')}
            aria-label={$t('management.artists.searchLabel')}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-brand transition-colors"
          />
        </div>
        <button
          onclick={refresh}
          disabled={loading}
          aria-label={$t('common.refresh')}
          class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
        </button>
      </div>
    </div>

    {#if selected.length > 0}
      <div class="px-6 py-3 bg-brand/10 border-y border-brand/20 flex items-center gap-3 flex-wrap" data-testid="bulk-bar">
        <span class="text-sm font-bold">{$t('management.artists.selectedCount', { count: selected.length })}</span>
        <button
          class="bg-brand text-black px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1"
          onclick={() => decideSelected(WHITE)}
        >
          <Check size={14} /> {$t('management.artists.approve')}
        </button>
        <button
          class="bg-red-500/10 text-red-400 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1"
          onclick={() => decideSelected(BLACK)}
        >
          <X size={14} /> {$t('management.artists.reject')}
        </button>
        <button
          class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 disabled:opacity-50"
          disabled={plan.decisions.length === 0}
          onclick={applySelectedProposals}
        >
          <Sparkles size={14} /> {$t('management.artists.applyProposals', { count: selected.length - plan.skipped.length })}
        </button>
        <button class="text-xs text-muma-spotify-text hover:text-white ml-auto" onclick={() => (selected = [])}>
          {$t('management.artists.clearSelection')}
        </button>
      </div>
    {/if}

    <div class="min-h-[200px]">
      {#if loading && rows.length === 0}
        <div class="flex items-center justify-center p-20">
          <RefreshCw class="animate-spin text-brand" size={32} />
        </div>
      {:else if rows.length === 0}
        <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
          <Users size={48} class="mb-4 opacity-20" />
          <p>
            {#if search}
              {$t('management.artists.noneForSearch', { search })}
            {:else if stateFilter === UNKNOWN}
              {$t('management.artists.queueEmpty')}
            {:else}
              {$t('management.artists.listEmpty')}
            {/if}
          </p>
        </div>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
                <th class="p-4 w-8">
                  <input
                    type="checkbox"
                    class="accent-brand"
                    aria-label={$t('management.artists.selectAll')}
                    checked={allVisibleSelected}
                    onchange={toggleAllVisible}
                  />
                </th>
                <th class="p-4">{$t('nav.artists')}</th>
                <th class="p-4">{$t('management.artists.tracks')}</th>
                <th class="p-4">{$t('management.artists.proposal')}</th>
                <th class="p-4">{$t('management.artists.outcome')}</th>
                <th class="p-4 text-right">{$t('management.artists.actions')}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each rows as row (row.name)}
                {@const proposal = describeProposal(row)}
                {@const outcome = describeOutcome(row)}
                {@const decision = describeDecision(row)}
                <tr class="hover:bg-white/5 transition-colors {selected.includes(row.name) ? 'bg-brand/5' : ''}">
                  <td class="p-4">
                    <input
                      type="checkbox"
                      class="accent-brand"
                      aria-label={$t('management.artists.selectName', { name: row.name })}
                      checked={selected.includes(row.name)}
                      onchange={() => toggleSelected(row.name)}
                    />
                  </td>
                  <td class="p-4">
                    <div class="font-bold">{row.name}</div>
                    {#if row.state !== UNKNOWN}
                      <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded {row.state === WHITE ? 'bg-brand/20 text-brand' : 'bg-red-500/10 text-red-500'}">
                        {$t(row.state === WHITE ? 'management.artists.filterWhite' : 'management.artists.filterBlack')}
                      </span>
                    {/if}
                  </td>
                  <td class="p-4 text-muma-spotify-text">{n(row.track_count)}</td>
                  <td class="p-4">
                    {#if proposal}
                      <div class="font-medium {row.proposal_kind === 'reject' ? 'text-red-400' : 'text-brand'}">{$t(proposal.key, proposal.vars)}</div>
                    {:else}
                      <div class="text-muma-spotify-text">{$t('management.artists.proposeNothing')}</div>
                    {/if}
                    {#if row.proposal_evidence?.length}
                      <ul class="text-[11px] text-muma-spotify-text m-0 mt-1 pl-3 list-disc">
                        {#each row.proposal_evidence as line, i (i)}
                          <li>{line}</li>
                        {/each}
                      </ul>
                    {/if}
                  </td>
                  <td class="p-4 text-muma-spotify-text">
                    <div>{$t(outcome.key, outcome.vars)}</div>
                    {#if decision}
                      <div class="text-xs mt-1">{decision.by ? $t('management.artists.decidedByAt', decision) : decision.when}</div>
                    {/if}
                  </td>
                  <td class="p-4 text-right">
                    <div class="flex justify-end gap-2">
                      {#if row.state !== WHITE}
                        <button
                          onclick={() => decideOne(row, WHITE)}
                          class="bg-brand text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <Check size={14} /> {$t('management.artists.approve')}
                        </button>
                      {/if}
                      {#if row.state !== BLACK || row.canonical_name}
                        <button
                          onclick={() => decideOne(row, BLACK)}
                          class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <X size={14} /> {$t('management.artists.reject')}
                        </button>
                      {/if}
                      <button
                        onclick={() => openCorrection(row)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                      >
                        <Replace size={14} /> {$t('management.artists.correct')}
                      </button>
                      {#if row.state !== UNKNOWN}
                        <button
                          onclick={() => undo(row)}
                          aria-label={$t('management.artists.undo', { name: row.name })}
                          class="text-muma-spotify-text hover:text-white px-2 flex items-center"
                        >
                          <Undo2 size={14} />
                        </button>
                      {/if}
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>

        <div class="px-6 py-3 flex items-center justify-between text-xs text-muma-spotify-text border-t border-white/5">
          <span>{$t('management.artists.page', paging)}</span>
          <div class="flex gap-2">
            <button class="p-1 hover:text-white disabled:opacity-30" disabled={offset === 0} aria-label={$t('management.artists.previousPage')} onclick={() => turnPage(-1)}>
              <ChevronLeft size={16} />
            </button>
            <button class="p-1 hover:text-white disabled:opacity-30" disabled={offset + PAGE_SIZE >= total} aria-label={$t('management.artists.nextPage')} onclick={() => turnPage(1)}>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      {/if}
    </div>
  </div>
</section>

{#if correcting}
  <div class="fixed inset-0 bg-black/80 flex items-center justify-center z-[1100] animate-in fade-in duration-200">
    <div class="bg-[#282828] p-8 rounded-xl border border-white/10 max-w-md w-full shadow-2xl">
      <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">
        <Replace class="text-brand" /> {correcting.name}
      </h3>
      <p class="text-muma-spotify-text mb-6">{$t('management.artists.correctionHelp')}</p>

      <label class="block mb-6">
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.artists.correctTo')}</span>
        <input
          type="text"
          bind:value={correctionTarget}
          placeholder={$t('management.artists.correctionPlaceholder')}
          class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand"
        />
      </label>

      {#if pendingCorrection.error}
        <p class="text-sm text-red-500 mb-4">{$t(pendingCorrection.error)}</p>
      {:else if correctionTarget.trim()}
        <p class="text-sm text-muma-spotify-text mb-6">
          {$t('management.artists.outcomeRewrite', { target: correctionTarget.trim() })} — {$t('management.artists.targetApproved')}
        </p>
      {/if}

      <div class="flex gap-4">
        <button
          class="flex-1 py-3 rounded-full font-bold bg-brand text-black hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100"
          disabled={!pendingCorrection.valid || !correctionTarget.trim()}
          onclick={saveCorrection}
        >
          {$t('common.save')}
        </button>
        <button
          class="flex-1 py-3 rounded-full font-bold bg-white/10 text-white hover:bg-white/20 transition-all"
          onclick={() => (correcting = null)}
        >
          {$t('common.cancel')}
        </button>
      </div>
    </div>
  </div>
{/if}
