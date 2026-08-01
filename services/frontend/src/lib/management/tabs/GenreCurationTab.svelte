<script>
  import { onMount } from 'svelte';
  import {
    RefreshCw,
    Search,
    Check,
    X,
    Replace,
    ListChecks,
    CircleSlash,
    CircleCheck,
    HelpCircle
  } from '@lucide/svelte';
  import {
    WHITE,
    BLACK,
    UNKNOWN,
    STATE_FILTERS,
    filterGenres,
    summarize,
    describeOutcome,
    describeDecision,
    buildDecision,
    correctionTargets
  } from '../genreCuration.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let rows = $state([]);
  let whiteGenres = $state([]);
  let loading = $state(false);
  let stateFilter = $state(UNKNOWN);
  let search = $state('');

  // The row being decided in the modal, plus the decision being composed for it.
  let deciding = $state(null);
  let decisionState = $state(WHITE);
  let decisionTargetIds = $state([]);

  const visibleRows = $derived(filterGenres(rows, search));
  const counts = $derived(summarize(rows));
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
      const query = stateFilter === 'all' ? '' : `state=${stateFilter}&`;
      const res = await fetch(`${API_BASE}/api/rules/genres?${query}limit=500`, {
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

  async function decide(row, state, canonicalIds = []) {
    const decision = buildDecision({ genreId: row.id, state, canonicalIds });
    if (!decision.valid) {
      onError(decision.error);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/rules/genres/${row.id}/decide`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(decision.payload)
      });
      if (res.ok) {
        const names = decision.payload.canonical_ids
          .map((id) => whiteGenres.find((g) => String(g.id) === String(id))?.name)
          .filter(Boolean);
        if (names.length) {
          onMessage(`${row.name} wordt voortaan vervangen door ${names.join(' + ')}.`);
        } else {
          onMessage(`${row.name} ${state === WHITE ? 'goedgekeurd' : 'afgekeurd'}.`);
        }
        deciding = null;
        await Promise.all([fetchGenres(), fetchWhiteGenres()]);
      } else {
        const data = await res.json();
        onError(data.detail || 'Beslissing opslaan mislukt.');
      }
    } catch (err) {
      onError('Netwerkfout bij opslaan beslissing.');
    }
  }

  function openCorrection(row) {
    deciding = row;
    decisionState = row.state === UNKNOWN ? BLACK : row.state;
    decisionTargetIds = (row.canonical_targets || []).map((target) => String(target.id));
  }

  $effect(() => {
    if (stateFilter) fetchGenres();
  });

  onMount(fetchWhiteGenres);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <ListChecks class="text-spotify-green" size={32} /> Genre Curatie
      </h2>
      <p class="text-spotify-lightgray">
        Keur genres goed, af of corrigeer ze. Beslissingen gelden vanaf de volgende tagger-run.
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
            placeholder="Zoek genre..."
            aria-label="Zoek genre"
            class="bg-spotify-dark border border-spotify-gray rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-spotify-green transition-colors"
          />
        </div>
        <button
          onclick={fetchGenres}
          disabled={loading}
          aria-label="Vernieuwen"
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
              <tr class="bg-white/5 text-spotify-lightgray text-[10px] uppercase tracking-wider">
                <th class="p-4">Genre</th>
                <th class="p-4">Voorkomens</th>
                <th class="p-4">Resultaat</th>
                <th class="p-4">Beslissing</th>
                <th class="p-4 text-right">Acties</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-spotify-gray divide-opacity-30">
              {#each visibleRows as row (row.id)}
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="p-4">
                    <div class="font-bold">{row.name}</div>
                    {#if row.state !== UNKNOWN}
                      <span
                        class="text-[10px] font-bold uppercase px-2 py-0.5 rounded {row.state === WHITE ? 'bg-spotify-green/20 text-spotify-green' : 'bg-red-500/10 text-red-500'}"
                      >
                        {row.state === WHITE ? 'Goedgekeurd' : 'Afgekeurd'}
                      </span>
                    {/if}
                  </td>
                  <td class="p-4 text-spotify-lightgray">{row.occurrences ?? 0}</td>
                  <td class="p-4 text-spotify-lightgray">{describeOutcome(row)}</td>
                  <td class="p-4 text-spotify-lightgray text-xs">{describeDecision(row)}</td>
                  <td class="p-4 text-right">
                    <div class="flex justify-end gap-2">
                      {#if row.state !== WHITE || (row.canonical_targets || []).length}
                        <button
                          onclick={() => decide(row, WHITE)}
                          class="bg-spotify-green text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <Check size={14} /> Goedkeuren
                        </button>
                      {/if}
                      {#if row.state !== BLACK || (row.canonical_targets || []).length}
                        <button
                          onclick={() => decide(row, BLACK)}
                          class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                        >
                          <X size={14} /> Afkeuren
                        </button>
                      {/if}
                      <button
                        onclick={() => openCorrection(row)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                      >
                        <Replace size={14} /> Corrigeren
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
        <Replace class="text-spotify-green" /> {deciding.name}
      </h3>
      <p class="text-spotify-lightgray mb-6">
        Kies wat er met dit genre gebeurt. Een correctie vervangt het genre door een goedgekeurd
        genre, ook als je het genre zelf afkeurt.
      </p>

      <div class="mb-6">
        <span class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">Status</span>
        <div class="flex gap-2">
          <button
            class="flex-1 py-2 rounded-full font-bold text-sm transition-all {decisionState === WHITE ? 'bg-spotify-green text-black' : 'bg-white/10 text-white hover:bg-white/20'}"
            onclick={() => (decisionState = WHITE)}
          >
            Goedkeuren
          </button>
          <button
            class="flex-1 py-2 rounded-full font-bold text-sm transition-all {decisionState === BLACK ? 'bg-red-600 text-white' : 'bg-white/10 text-white hover:bg-white/20'}"
            onclick={() => (decisionState = BLACK)}
          >
            Afkeuren
          </button>
        </div>
      </div>

      <div class="mb-6">
        <span class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">
          Corrigeren naar (optioneel, meerdere mag)
        </span>
        <p class="text-xs text-spotify-lightgray mb-2">
          Kies er meerdere voor een samentrekking: <b>Upterror</b> is Uptempo Hardcore én Terror.
        </p>
        <div class="max-h-48 overflow-y-auto rounded-md border border-spotify-gray bg-spotify-gray bg-opacity-30 divide-y divide-white/5">
          {#each targets as target (target.id)}
            <label class="flex items-center gap-3 px-3 py-2 text-sm cursor-pointer hover:bg-white/5">
              <input
                type="checkbox"
                checked={decisionTargetIds.includes(String(target.id))}
                onchange={() => toggleTarget(target.id)}
                class="accent-spotify-green"
              />
              {target.name}
            </label>
          {:else}
            <p class="px-3 py-2 text-sm text-spotify-lightgray">Nog geen goedgekeurde genres om naar te corrigeren.</p>
          {/each}
        </div>
      </div>

      <p class="text-sm text-spotify-lightgray mb-6">
        Resultaat: <span class="text-white font-bold">{previewOutcome}</span>
      </p>

      {#if pendingDecision.error}
        <p class="text-sm text-red-500 mb-4">{pendingDecision.error}</p>
      {/if}

      <div class="flex gap-4">
        <button
          class="flex-1 py-3 rounded-full font-bold bg-spotify-green text-black hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100"
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
