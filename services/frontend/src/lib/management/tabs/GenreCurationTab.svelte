<script>
  import { t } from '../../i18n/index.js';
  import { onMount, onDestroy } from 'svelte';
  import {
    RefreshCw,
    Search,
    Check,
    X,
    Replace,
    ListChecks,
    CircleSlash,
    CircleCheck,
    HelpCircle,
    Sparkles
  } from '@lucide/svelte';
  import {
    WHITE,
    BLACK,
    UNKNOWN,
    STATE_FILTERS,
    PROPOSAL_FILTERS,
    BULK_CONFIDENCE_FLOOR,
    filterGenres,
    summarize,
    describeOutcome,
    describeDecision,
    describeProposal,
    decisionFromProposal,
    planFromProposals,
    buildDecision,
    correctionTargets
  } from '../genreCuration.js';
  import { SECTIONS } from '../genreRules.js';
  import GenreRulesPanel from '../GenreRulesPanel.svelte';
  import GenreOverviewPanel from '../GenreOverviewPanel.svelte';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  // Which part of the page is open: the queue with its advice, the approved genres,
  // or one of the two rule tables. The queue's own state filter lives inside it.
  let section = $state('queue');
  // Bumped when a rule panel changes something, so the overview's counts follow.
  let rulesVersion = $state(0);

  let rows = $state([]);
  let whiteGenres = $state([]);
  let loading = $state(false);
  let stateFilter = $state(UNKNOWN);
  let proposalFilter = $state(null);
  let search = $state('');

  // What the analysis knows: queue size, advice per kind, when it last ran.
  let summary = $state(null);
  // The analysis job, while one runs. Polled rather than streamed: a run is
  // seconds, and the job endpoint is what the artist page polls too.
  let analysisJob = $state(null);
  let pollTimer = null;
  // The bulk apply in flight, so the button cannot be pressed twice.
  let applying = $state(false);

  // The row being decided in the modal, plus the decision being composed for it.
  let deciding = $state(null);
  let decisionState = $state(WHITE);
  let decisionTargetIds = $state([]);

  const visibleRows = $derived(filterGenres(rows, search));
  const counts = $derived(summarize(rows));
  const plan = $derived(stateFilter === UNKNOWN ? planFromProposals(visibleRows) : { applicable: [], skipped: [] });
  const targets = $derived(correctionTargets(whiteGenres, deciding?.id));
  const pendingDecision = $derived(
    deciding
      ? buildDecision({ genreId: deciding.id, state: decisionState, canonicalIds: decisionTargetIds })
      : { valid: false, error: null }
  );
  const previewOutcome = $derived(
    deciding
      ? describeOutcome({
          state: decisionState,
          canonical_targets: decisionTargetIds
            .map((id) => whiteGenres.find((g) => String(g.id) === String(id)))
            .filter(Boolean)
        })
      : ''
  );

  function toggleTarget(id) {
    const key = String(id);
    decisionTargetIds = decisionTargetIds.includes(key)
      ? decisionTargetIds.filter((existing) => existing !== key)
      : [...decisionTargetIds, key];
  }

  async function fetchGenres() {
    loading = true;
    try {
      const params = [];
      if (stateFilter !== 'all') params.push(`state=${stateFilter}`);
      if (stateFilter === UNKNOWN && proposalFilter) params.push(`proposal=${proposalFilter}`);
      params.push('limit=500');
      const res = await fetch(`${API_BASE}/api/rules/genres?${params.join('&')}`, {
        headers: getHeaders()
      });
      if (res.ok) {
        rows = await res.json();
      } else {
        onError('Kon genres niet ophalen.');
      }
    } catch (err) {
      onError('Netwerkfout bij ophalen genres.');
    } finally {
      loading = false;
    }
  }

  /**
   * The approved genres, kept separate from the table: they are the only valid
   * correction targets, and stay needed while the table shows the unknown queue.
   */
  async function fetchWhiteGenres() {
    try {
      const res = await fetch(`${API_BASE}/api/rules/genres?state=${WHITE}&limit=1000`, {
        headers: getHeaders()
      });
      if (res.ok) whiteGenres = await res.json();
    } catch (err) {
      console.error('Kon goedgekeurde genres niet ophalen:', err);
    }
  }

  async function fetchSummary() {
    try {
      const res = await fetch(`${API_BASE}/api/rules/genres/summary`, { headers: getHeaders() });
      if (res.ok) summary = await res.json();
    } catch (err) {
      console.error('Kon samenvatting niet ophalen:', err);
    }
  }

  /**
   * Post one decision. Returns the names it rewrites to, or null when the API
   * refused -- the caller decides whether that is a message or a tally.
   */
  async function postDecision(row, state, canonicalIds = []) {
    const decision = buildDecision({ genreId: row.id, state, canonicalIds });
    if (!decision.valid) {
      onError(decision.error);
      return null;
    }
    try {
      const res = await fetch(`${API_BASE}/api/rules/genres/${row.id}/decide`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(decision.payload)
      });
      if (!res.ok) {
        const data = await res.json();
        onError(data.detail || $t('management.genres.saveFailed'));
        return null;
      }
      return decision.payload.canonical_ids
        .map((id) => whiteGenres.find((g) => String(g.id) === String(id))?.name)
        .filter(Boolean);
    } catch (err) {
      onError($t('management.genres.saveNetworkError'));
      return null;
    }
  }

  async function refresh() {
    await Promise.all([fetchGenres(), fetchWhiteGenres(), fetchSummary()]);
  }

  async function decide(row, state, canonicalIds = []) {
    const names = await postDecision(row, state, canonicalIds);
    if (names === null) return;
    if (names.length) {
      onMessage(`${row.name} wordt voortaan vervangen door ${names.join(' + ')}.`);
    } else {
      onMessage(`${row.name} ${state === WHITE ? 'goedgekeurd' : 'afgekeurd'}.`);
    }
    deciding = null;
    await refresh();
  }

  /** One row's advice, as the decision it amounts to. */
  async function applyProposal(row) {
    const decision = decisionFromProposal(row);
    if (!decision) return;
    await decide(row, decision.state, decision.canonicalIds);
  }

  /**
   * Every confident piece of advice on the page, one decision each. Sequential
   * rather than parallel: each decision marks files for a retag and refreshes the
   * tagger's rules, and a burst of those is what the proxy refuses.
   */
  async function applyAllProposals() {
    if (applying || !plan.applicable.length) return;
    applying = true;
    let applied = 0;
    try {
      for (const row of plan.applicable) {
        const decision = decisionFromProposal(row);
        if (decision && (await postDecision(row, decision.state, decision.canonicalIds)) !== null) applied += 1;
      }
    } finally {
      applying = false;
    }
    onMessage($t('management.genres.proposalsApplied', { applied, skipped: plan.skipped.length }));
    await refresh();
  }

  async function startAnalysis() {
    try {
      const res = await fetch(`${API_BASE}/api/rules/genres/analyze`, { method: 'POST', headers: getHeaders() });
      if (!res.ok) {
        onError($t('management.genres.analysisFailed'));
        return;
      }
      const body = await res.json();
      analysisJob = { id: body.job_id, status: body.status };
      pollAnalysis();
    } catch {
      onError($t('management.genres.saveNetworkError'));
    }
  }

  async function pollAnalysis() {
    if (!analysisJob) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/genres/analyze/${analysisJob.id}`, { headers: getHeaders() });
      if (res.ok) {
        const status = await res.json();
        analysisJob = { ...analysisJob, ...status };
        if (status.status === 'finished') {
          onMessage($t('management.genres.analysisDone', { count: status.total ?? 0 }));
          analysisJob = null;
          await refresh();
          return;
        }
        if (status.status === 'failed') {
          onError(status.error || $t('management.genres.analysisFailed'));
          analysisJob = null;
          return;
        }
      }
    } catch (err) {
      console.error('Kon analyse-status niet ophalen:', err);
    }
    pollTimer = setTimeout(pollAnalysis, 2000);
  }

  function setProposalFilter(id) {
    proposalFilter = id;
    fetchGenres();
  }

  function openCorrection(row) {
    deciding = row;
    decisionState = row.state === UNKNOWN ? BLACK : row.state;
    decisionTargetIds = (row.canonical_targets || []).map((target) => String(target.id));
  }

  $effect(() => {
    if (stateFilter) fetchGenres();
  });

  // The first visit has no advice to show, so the analysis starts on its own;
  // after that it is the button, because a run rewrites every proposal.
  onMount(async () => {
    await Promise.all([fetchWhiteGenres(), fetchSummary()]);
    if (summary && !summary.analyzed_at && !analysisJob) await startAnalysis();
  });
  onDestroy(() => clearTimeout(pollTimer));
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <ListChecks class="text-brand" size={32} /> {$t('management.tabs.genreCuration')}
      </h2>
      <p class="text-muma-spotify-text">
        {$t('management.genres.subtitle')}
      </p>
    </div>

    {#if section === 'queue'}
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
    {/if}
  </header>

  <nav class="flex gap-6 border-b border-white/10" aria-label={$t('management.genres.sections')}>
    {#each SECTIONS as item (item.id)}
      <button
        type="button"
        class="pb-4 font-bold text-sm transition-colors relative {section === item.id ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
        aria-current={section === item.id ? 'page' : undefined}
        onclick={() => (section = item.id)}
      >
        {$t(item.labelKey)}
        {#if section === item.id}
          <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
        {/if}
      </button>
    {/each}
  </nav>

  {#if section === 'overview'}
    <GenreOverviewPanel {API_BASE} {getHeaders} {onError} refreshKey={rulesVersion} />
  {:else if section === 'artist-rules'}
    <GenreRulesPanel {API_BASE} {getHeaders} {onMessage} {onError} kind="artist" {whiteGenres} onchange={() => (rulesVersion += 1)} />
  {:else if section === 'label-rules'}
    <GenreRulesPanel {API_BASE} {getHeaders} {onMessage} {onError} kind="label" {whiteGenres} onchange={() => (rulesVersion += 1)} />
  {/if}

  {#if section === 'queue' && summary}
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">{$t('management.genres.queue')}</p>
        <p class="text-2xl font-extrabold m-0">{summary.unknown ?? 0}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">Goedgekeurd</p>
        <p class="text-2xl font-extrabold m-0 text-brand">{summary.white ?? 0}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">Afgekeurd</p>
        <p class="text-2xl font-extrabold m-0 text-red-400">{summary.black ?? 0}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4 flex flex-col gap-2">
        <p class="text-[10px] uppercase tracking-wider text-muma-spotify-text m-0">{$t('management.genres.proposals')}</p>
        <p class="text-sm m-0">
          {$t('management.genres.proposalCounts', {
            rewrite: (summary.proposals?.rewrite ?? 0) + (summary.proposals?.split ?? 0),
            reject: summary.proposals?.reject ?? 0
          })}
        </p>
        <button
          class="self-start bg-white/10 hover:bg-white/20 text-white px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 disabled:opacity-50"
          disabled={Boolean(analysisJob)}
          onclick={startAnalysis}
        >
          <Sparkles size={14} />
          {analysisJob ? $t('management.genres.analysing') : $t('management.genres.analyse')}
        </button>
        <p class="text-[11px] text-muma-spotify-text m-0">
          {summary.analyzed_at ? $t('management.genres.analysedAt', { when: summary.analyzed_at }) : $t('management.genres.neverAnalysed')}
        </p>
      </div>
    </div>
  {/if}

  {#if section === 'queue'}
  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
      <h3 class="text-xl font-bold flex items-center gap-2">
        {#if stateFilter === UNKNOWN}<HelpCircle size={20} class="text-yellow-500" />{/if}
        {#if stateFilter === WHITE}<CircleCheck size={20} class="text-brand" />{/if}
        {#if stateFilter === BLACK}<CircleSlash size={20} class="text-red-500" />{/if}
        {STATE_FILTERS.find((f) => f.id === stateFilter)?.label}
        <span class="text-muma-spotify-text text-sm font-normal">({counts.total})</span>
      </h3>

      <div class="flex items-center gap-3 flex-wrap">
        {#if stateFilter === UNKNOWN}
          <div class="flex bg-muma-spotify-dark p-1 rounded-full border border-white/5" role="group" aria-label={$t('management.genres.proposals')}>
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
          <button
            class="bg-brand/20 text-brand border border-brand/30 px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 disabled:opacity-50"
            disabled={applying || plan.applicable.length === 0}
            title={$t('management.genres.applyProposalsHelp', { floor: BULK_CONFIDENCE_FLOOR })}
            onclick={applyAllProposals}
          >
            <Sparkles size={14} />
            {$t('management.genres.applyProposals', { count: plan.applicable.length })}
          </button>
        {/if}
        <div class="relative">
          <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" />
          <input
            type="text"
            bind:value={search}
            placeholder={$t('management.genres.searchPlaceholder')}
            aria-label={$t('management.genres.searchLabel')}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-brand transition-colors"
          />
        </div>
        <button
          onclick={fetchGenres}
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
          <ListChecks size={48} class="mb-4 opacity-20" />
          <p>
            {#if search}
              Geen genre gevonden voor '{search}'.
            {:else if stateFilter === UNKNOWN}
              Niets te beoordelen. Alle genres hebben een beslissing.
            {:else}
              Geen genres in deze lijst.
            {/if}
          </p>
        </div>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
                <th class="p-4">{$t('nav.genres')}</th>
                <th class="p-4">{$t('management.genres.occurrences')}</th>
                {#if stateFilter === UNKNOWN}
                  <th class="p-4">{$t('management.genres.proposal')}</th>
                {/if}
                <th class="p-4">{$t('management.genres.outcome')}</th>
                <th class="p-4">{$t('management.genres.decision')}</th>
                <th class="p-4 text-right">{$t('management.genres.actions')}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each visibleRows as row (row.id)}
                {@const proposal = describeProposal(row)}
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="p-4">
                    <div class="font-bold">{row.name}</div>
                    {#if row.state !== UNKNOWN}
                      <span
                        class="text-[10px] font-bold uppercase px-2 py-0.5 rounded {row.state === WHITE ? 'bg-brand/20 text-brand' : 'bg-red-500/10 text-red-500'}"
                      >
                        {row.state === WHITE ? 'Goedgekeurd' : 'Afgekeurd'}
                      </span>
                    {/if}
                  </td>
                  <td class="p-4 text-muma-spotify-text">{row.occurrences ?? 0}</td>
                  {#if stateFilter === UNKNOWN}
                    <td class="p-4">
                      {#if proposal}
                        <div class="font-medium flex items-center gap-2 {row.proposal?.kind === 'reject' ? 'text-red-400' : 'text-brand'}">
                          {$t(proposal.key, proposal.vars)}
                          <span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/10 text-muma-spotify-text" title={$t('management.genres.confidence')}>
                            {row.proposal?.confidence ?? 0}%
                          </span>
                        </div>
                      {:else}
                        <div class="text-muma-spotify-text">{$t('management.genres.proposeNothing')}</div>
                      {/if}
                      {#if row.proposal?.evidence?.length}
                        <ul class="text-[11px] text-muma-spotify-text m-0 mt-1 pl-3 list-disc">
                          {#each row.proposal.evidence as line, i (i)}
                            <li>{line}</li>
                          {/each}
                        </ul>
                      {/if}
                    </td>
                  {/if}
                  <td class="p-4 text-muma-spotify-text">{describeOutcome(row)}</td>
                  <td class="p-4 text-muma-spotify-text text-xs">{describeDecision(row)}</td>
                  <td class="p-4 text-right">
                    <div class="flex justify-end gap-2">
                      {#if stateFilter === UNKNOWN && decisionFromProposal(row)}
                        <button
                          onclick={() => applyProposal(row)}
                          class="bg-brand/20 text-brand border border-brand/30 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <Sparkles size={14} /> {$t('management.genres.applyProposal')}
                        </button>
                      {/if}
                      {#if row.state !== WHITE || (row.canonical_targets || []).length}
                        <button
                          onclick={() => decide(row, WHITE)}
                          class="bg-brand text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <Check size={14} /> {$t('management.genres.approve')}
                        </button>
                      {/if}
                      {#if row.state !== BLACK || (row.canonical_targets || []).length}
                        <button
                          onclick={() => decide(row, BLACK)}
                          class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <X size={14} /> {$t('management.genres.reject')}
                        </button>
                      {/if}
                      <button
                        onclick={() => openCorrection(row)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                      >
                        <Replace size={14} /> {$t('management.genres.correct')}
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
  {/if}
</section>

{#if deciding}
  <div class="fixed inset-0 bg-black/80 flex items-center justify-center z-[1100] animate-in fade-in duration-200">
    <div class="bg-[#282828] p-8 rounded-xl border border-white/10 max-w-md w-full shadow-2xl">
      <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">
        <Replace class="text-brand" /> {deciding.name}
      </h3>
      <p class="text-muma-spotify-text mb-6">
        {$t('management.genres.decisionHelp')}
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
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">
          {$t('management.genres.correctTo')}
        </span>
        <p class="text-xs text-muma-spotify-text mb-2">
          {$t('management.genres.pickMultiple')}
        </p>
        <div class="max-h-48 overflow-y-auto rounded-md border border-muma-spotify-panel bg-muma-spotify-panel/30 divide-y divide-white/5">
          {#each targets as target (target.id)}
            <label class="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-white/5">
              <input
                type="checkbox"
                checked={decisionTargetIds.includes(String(target.id))}
                onchange={() => toggleTarget(target.id)}
                class="accent-brand"
              />
              {target.name}
            </label>
          {:else}
            <p class="px-3 py-2 text-sm text-muma-spotify-text">{$t('management.genres.noApprovedGenres')}</p>
          {/each}
        </div>
      </div>

      <p class="text-sm text-muma-spotify-text mb-6">
        {$t('management.genres.outcomeIs', { outcome: previewOutcome })}
      </p>

      {#if pendingDecision.error}
        <p class="text-sm text-red-500 mb-4">{pendingDecision.error}</p>
      {/if}

      <div class="flex gap-4">
        <button
          class="flex-1 py-3 rounded-full font-bold bg-brand text-black hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100"
          disabled={!pendingDecision.valid}
          onclick={() => decide(deciding, decisionState, decisionTargetIds)}
        >
          Opslaan
        </button>
        <button
          class="flex-1 py-3 rounded-full font-bold bg-white/10 text-white hover:bg-white/20 transition-all"
          onclick={() => (deciding = null)}
        >
          Annuleren
        </button>
      </div>
    </div>
  </div>
{/if}
