<script>
  /**
   * The rules that give a track a genre from its artist or from its label -- one
   * panel for both, told apart by `kind`. Lists every rule with its reach (how many
   * tracks the artist or label has) and who made it, adds one from a name and an
   * approved genre, removes one. Editing the artist or label itself is the player's
   * edit page, reached from the row.
   *
   * The whole list is loaded at once: a few hundred rules, and filtering them
   * client-side is what lets the box match on genre as well as on name.
   */
  import { format, t } from '../i18n/index.js';
  import { onDestroy, onMount } from 'svelte';
  import { RefreshCw, Search, Trash2, Plus, Pencil } from '@lucide/svelte';
  import { activeView } from '../store.js';
  import { RULE_KINDS, RULE_SORTS, buildRule, describeRule, filterRules, sortRules, subjectOf } from './genreRules.js';

  let { API_BASE, getHeaders, onMessage, onError, kind = 'artist', whiteGenres = [], onchange } = $props();

  const spec = $derived(RULE_KINDS[kind]);

  let rows = $state([]);
  let loading = $state(false);
  let search = $state('');
  let sort = $state('name');

  // The add form: a name typed or picked from the library search, and a genre.
  let newName = $state('');
  let newGenreId = $state('');
  let suggestions = $state([]);
  let searchTimer = null;
  let saving = $state(false);

  const visibleRows = $derived(sortRules(kind, filterRules(kind, rows, search), sort));
  const pending = $derived(buildRule(kind, { name: newName, genreId: newGenreId, existing: rows }));
  const n = (value) => $format.number(value);

  async function fetchRows() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}${spec.rulesPath}`, { headers: getHeaders() });
      if (res.ok) {
        rows = await res.json();
      } else {
        onError($t('management.genres.rulesLoadFailed'));
      }
    } catch {
      onError($t('management.genres.rulesLoadNetworkError'));
    } finally {
      loading = false;
    }
  }

  /** Library names matching what was typed, for the datalist under the name box. */
  function onNameInput(event) {
    newName = event.currentTarget.value;
    clearTimeout(searchTimer);
    const query = newName.trim();
    if (query.length < 2) {
      suggestions = [];
      return;
    }
    searchTimer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}${spec.searchPath}?q=${encodeURIComponent(query)}`, {
          headers: getHeaders()
        });
        if (res.ok) suggestions = await res.json();
      } catch {
        // The box still accepts what was typed; the suggestions are a convenience.
      }
    }, 250);
  }

  async function addRule() {
    if (!pending.valid || saving) return;
    saving = true;
    try {
      const res = await fetch(`${API_BASE}${spec.rulesPath}`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(pending.payload)
      });
      if (res.ok) {
        const genre = whiteGenres.find((g) => String(g.id) === String(newGenreId));
        onMessage($t('management.genres.ruleAdded', { name: pending.payload[spec.nameField], genre: genre?.name ?? '' }));
        newName = '';
        suggestions = [];
        await fetchRows();
        onchange?.();
      } else {
        const data = await res.json().catch(() => ({}));
        onError(data.detail || $t('management.tagger.addRuleFailed'));
      }
    } catch {
      onError($t('management.tagger.addRuleFailed'));
    } finally {
      saving = false;
    }
  }

  async function removeRule(row) {
    try {
      const res = await fetch(`${API_BASE}${spec.rulesPath}/${row.id}`, { method: 'DELETE', headers: getHeaders() });
      if (res.ok) {
        onMessage($t('management.tagger.ruleDeleted'));
        await fetchRows();
        onchange?.();
      } else {
        onError($t('management.tagger.deleteRuleFailed'));
      }
    } catch {
      onError($t('management.tagger.deleteRuleFailed'));
    }
  }

  /** The edit page is a view of the player, not a management tab: leave Beheer for it. */
  function edit(row) {
    const view = spec.editView(row);
    if (view) activeView.set(view);
  }

  onMount(fetchRows);
  onDestroy(() => clearTimeout(searchTimer));
</script>

<div class="space-y-6" data-testid="genre-rules-{kind}">
  <form
    class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-6 grid grid-cols-1 md:grid-cols-[1fr_1fr_auto] gap-4 items-end"
    onsubmit={(event) => {
      event.preventDefault();
      addRule();
    }}
  >
    <div>
      <label for="rule-name-{kind}" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">
        {$t(spec.subjectKey)}
      </label>
      <input
        id="rule-name-{kind}"
        type="text"
        list="rule-suggestions-{kind}"
        value={newName}
        oninput={onNameInput}
        placeholder={$t('management.tagger.namePlaceholder')}
        autocomplete="off"
        class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 text-sm focus:outline-none focus:border-brand"
      />
      <datalist id="rule-suggestions-{kind}">
        {#each suggestions as suggestion (suggestion.id ?? suggestion.name)}
          <option value={suggestion.name}></option>
        {/each}
      </datalist>
    </div>
    <div>
      <label for="rule-genre-{kind}" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">
        {$t('management.tagger.pickGenre')}
      </label>
      <select
        id="rule-genre-{kind}"
        bind:value={newGenreId}
        class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 text-sm focus:outline-none focus:border-brand"
      >
        <option value="">{$t('management.tagger.select')}</option>
        {#each whiteGenres as genre (genre.id)}
          <option value={String(genre.id)}>{genre.name}</option>
        {/each}
      </select>
    </div>
    <button
      type="submit"
      disabled={!pending.valid || saving}
      title={pending.error ? $t(pending.error) : ''}
      class="bg-brand text-black font-extrabold px-5 py-3 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100 flex items-center gap-2"
    >
      <Plus size={16} /> {$t('management.genres.ruleAdd')}
    </button>
    {#if newName && pending.error === 'management.genres.ruleExists'}
      <p class="text-xs text-yellow-500 m-0 md:col-span-3">{$t(pending.error)}</p>
    {/if}
  </form>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
      <h3 class="text-xl font-bold flex items-center gap-2">
        {$t(spec.labelKey)}
        <span class="text-muma-spotify-text text-sm font-normal">({n(visibleRows.length)}{search ? ` / ${n(rows.length)}` : ''})</span>
      </h3>
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex bg-muma-spotify-dark p-1 rounded-full border border-white/5" role="group" aria-label={$t('management.genres.ruleSort')}>
          {#each RULE_SORTS as option (option)}
            <button
              type="button"
              class="px-3 py-1 rounded-full text-xs font-bold transition-colors {sort === option ? 'bg-white text-black' : 'text-muma-spotify-text hover:text-white'}"
              aria-pressed={sort === option}
              onclick={() => (sort = option)}
            >
              {$t(`management.genres.ruleSort_${option}`)}
            </button>
          {/each}
        </div>
        <div class="relative">
          <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" />
          <input
            type="text"
            bind:value={search}
            placeholder={$t('management.genres.ruleSearchPlaceholder')}
            aria-label={$t('management.genres.ruleSearchPlaceholder')}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-brand transition-colors"
          />
        </div>
        <button
          type="button"
          onclick={fetchRows}
          disabled={loading}
          aria-label={$t('common.refresh')}
          class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
        >
          <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
        </button>
      </div>
    </div>

    {#if loading && rows.length === 0}
      <div class="flex items-center justify-center p-20"><RefreshCw class="animate-spin text-brand" size={32} /></div>
    {:else if visibleRows.length === 0}
      <p class="p-12 text-center text-muma-spotify-text">
        {search ? $t('management.genres.ruleNoneFor', { query: search }) : $t('management.genres.ruleNone')}
      </p>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
              <th class="p-4">{$t(spec.subjectKey)}</th>
              <th class="p-4">{$t('nav.genres')}</th>
              <th class="p-4">{$t('management.artists.tracks')}</th>
              <th class="p-4">{$t('management.genres.ruleBy')}</th>
              <th class="p-4 text-right">{$t('management.genres.actions')}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30">
            {#each visibleRows as row (row.id)}
              {@const provenance = describeRule(row)}
              <tr class="hover:bg-white/5 transition-colors">
                <td class="p-4 font-bold">
                  {subjectOf(kind, row)}
                  {#if !row[spec.subjectIdField]}
                    <span class="ml-2 text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-500" title={$t('management.genres.ruleOrphanHelp')}>
                      {$t('management.genres.ruleOrphan')}
                    </span>
                  {/if}
                </td>
                <td class="p-4">
                  <span class="px-2 py-1 bg-muma-spotify-dark rounded text-brand text-xs font-bold">{row.genre_name}</span>
                </td>
                <td class="p-4 text-muma-spotify-text">{n(row.track_count)}</td>
                <td class="p-4 text-muma-spotify-text text-xs">
                  {#if provenance}
                    {provenance.by ? `${provenance.by} · ${provenance.when}` : provenance.when}
                  {:else}
                    —
                  {/if}
                </td>
                <td class="p-4 text-right">
                  <div class="flex justify-end gap-2">
                    {#if spec.editView(row)}
                      <button
                        type="button"
                        onclick={() => edit(row)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 hover:scale-105 transition-transform"
                      >
                        <Pencil size={14} /> {$t('common.edit')}
                      </button>
                    {/if}
                    <button
                      type="button"
                      onclick={() => removeRule(row)}
                      aria-label={$t('management.genres.ruleRemove', { name: subjectOf(kind, row) })}
                      class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 hover:scale-105 transition-transform"
                    >
                      <Trash2 size={14} /> {$t('management.genres.ruleRemoveShort')}
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
