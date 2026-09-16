<script>
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { RefreshCw, Plus, Trash2, ListTree, Check, X, Search as SearchIcon } from '@lucide/svelte';
  import { buildLineup, fieldsFromId, groupByFestival, replaceName } from '../lineups.js';

  /**
   * The festival lineups: one text file per edition (or per stage) under the music
   * share, one artist per line, which the browse pages filter on. The editor is a
   * pasted bill; "Controleren" says which lines the library can match before anything
   * is written, because the filter compares the whole display name and a spelling
   * the library stores differently matches nothing. A suggestion is one click to
   * take over.
   */
  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let lineups = $state([]);
  let root = $state('');
  let loading = $state(false);
  let selectedId = $state(null);
  let form = $state({ festival: '', year: '', stage: '', text: '' });
  let report = $state(null);
  let checking = $state(false);
  let saving = $state(false);

  const groups = $derived(groupByFestival(lineups));
  const pending = $derived(buildLineup(form));

  async function fetchLineups() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/rules/lineups`, { headers: getHeaders() });
      if (res.ok) {
        const body = await res.json();
        lineups = body.lineups || [];
        root = body.root || '';
      } else {
        onError($t('management.lineups.loadFailed'));
      }
    } catch {
      onError($t('management.lineups.loadNetworkError'));
    } finally {
      loading = false;
    }
  }

  async function open(lineup) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/lineups/${lineup.id.split('/').map(encodeURIComponent).join('/')}`, {
        headers: getHeaders()
      });
      if (!res.ok) {
        onError($t('management.lineups.loadFailed'));
        return;
      }
      const body = await res.json();
      selectedId = lineup.id;
      form = { ...fieldsFromId(lineup.id), text: (body.names || []).join('\n') };
      report = body.match || null;
    } catch {
      onError($t('management.lineups.loadNetworkError'));
    }
  }

  function startNew() {
    selectedId = null;
    form = { festival: '', year: '', stage: '', text: '' };
    report = null;
  }

  async function check() {
    if (!form.text.trim()) return;
    checking = true;
    try {
      const res = await fetch(`${API_BASE}/api/rules/lineups/match`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ text: form.text })
      });
      if (res.ok) report = (await res.json()).match || null;
      else onError($t('management.lineups.loadFailed'));
    } catch {
      onError($t('management.lineups.loadNetworkError'));
    } finally {
      checking = false;
    }
  }

  function takeSuggestion(name, replacement) {
    form.text = replaceName(form.text, name, replacement);
    if (report) {
      report = {
        ...report,
        matched: [...report.matched, replacement],
        unmatched: report.unmatched.filter((entry) => entry !== name)
      };
    }
  }

  async function save() {
    if (!pending.valid) {
      onError($t(pending.error));
      return;
    }
    saving = true;
    try {
      const res = await fetch(`${API_BASE}/api/rules/lineups`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(pending.payload)
      });
      if (res.ok) {
        const body = await res.json();
        report = body.match || null;
        selectedId = body.id;
        form = { ...form, text: (body.names || []).join('\n') };
        onMessage(
          $t('management.lineups.saved', {
            id: body.id,
            matched: body.match?.matched?.length ?? 0,
            total: body.names?.length ?? 0
          })
        );
        await fetchLineups();
      } else {
        const data = await res.json().catch(() => ({}));
        onError(data.detail || $t('management.lineups.saveFailed'));
      }
    } catch {
      onError($t('management.lineups.saveNetworkError'));
    } finally {
      saving = false;
    }
  }

  async function remove(lineup) {
    if (!confirm($t('management.lineups.confirmDelete', { id: lineup.id }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/lineups/${lineup.id.split('/').map(encodeURIComponent).join('/')}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.lineups.deleted', { id: lineup.id }));
        if (selectedId === lineup.id) startNew();
        await fetchLineups();
      } else {
        const data = await res.json().catch(() => ({}));
        onError(data.detail || $t('management.lineups.saveFailed'));
      }
    } catch {
      onError($t('management.lineups.saveNetworkError'));
    }
  }

  onMount(fetchLineups);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500" data-testid="lineups-tab">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <ListTree class="text-brand" size={32} /> {$t('management.tabs.lineups')}
      </h2>
      <p class="text-muma-spotify-text">{$t('management.lineups.subtitle')}</p>
      {#if root}
        <p class="text-xs text-muma-spotify-text mt-1 font-mono">{root}</p>
      {/if}
    </div>
    <button class="bg-brand text-black px-4 py-2 rounded-full font-bold text-sm flex items-center gap-2 hover:scale-105 transition-transform" onclick={startNew}>
      <Plus size={16} /> {$t('management.lineups.new')}
    </button>
  </header>

  <div class="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
      <div class="p-4 bg-black/20 flex justify-between items-center">
        <h3 class="font-bold">{$t('management.lineups.files')} <span class="text-muma-spotify-text text-sm font-normal">({lineups.length})</span></h3>
        <button onclick={fetchLineups} disabled={loading} aria-label={$t('common.refresh')} class="text-muma-spotify-text hover:text-white disabled:opacity-50">
          <RefreshCw size={16} class={loading ? 'animate-spin' : ''} />
        </button>
      </div>
      {#if groups.length === 0}
        <p class="p-6 text-sm text-muma-spotify-text">{$t('management.lineups.empty')}</p>
      {:else}
        <ul class="list-none m-0 p-2 max-h-[60vh] overflow-y-auto">
          {#each groups as group (group.festival)}
            <li class="mb-2">
              <div class="px-2 py-1 text-[10px] uppercase tracking-wider text-muma-spotify-text font-bold">{group.festival}</div>
              {#each group.lineups as lineup (lineup.id)}
                <div class="flex items-center gap-1">
                  <button
                    class="flex-1 text-left px-3 py-1.5 rounded-md text-sm flex justify-between gap-2 {selectedId === lineup.id ? 'bg-white/10 text-white' : 'text-muma-spotify-text hover:text-white hover:bg-white/5'}"
                    onclick={() => open(lineup)}
                  >
                    <span>{lineup.year ? `${lineup.year}${lineup.stage ? ` · ${lineup.stage}` : ''}` : $t('management.lineups.wholeFestival')}</span>
                    <span class="text-xs opacity-60">{lineup.artists}</span>
                  </button>
                  <button onclick={() => remove(lineup)} aria-label={$t('management.lineups.delete', { id: lineup.id })} class="text-muma-spotify-text hover:text-red-400 px-1"><Trash2 size={14} /></button>
                </div>
              {/each}
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-6 flex flex-col gap-4" data-testid="lineup-editor">
      <h3 class="font-bold text-lg">{selectedId ? selectedId : $t('management.lineups.new')}</h3>
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label class="block">
          <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.lineups.festival')}</span>
          <input type="text" bind:value={form.festival} class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand" />
        </label>
        <label class="block">
          <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.lineups.year')}</span>
          <input type="text" bind:value={form.year} placeholder="2025" class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand" />
        </label>
        <label class="block">
          <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.lineups.stage')}</span>
          <input type="text" bind:value={form.stage} placeholder="RED" class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand" />
        </label>
      </div>
      <p class="text-xs text-muma-spotify-text m-0">{$t('management.lineups.pathHelp')}</p>
      <label class="block">
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.lineups.bill')}</span>
        <textarea bind:value={form.text} rows="14" placeholder={$t('management.lineups.billPlaceholder')} aria-label={$t('management.lineups.bill')} class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand font-mono"></textarea>
      </label>

      {#if pending.error && form.text.trim()}
        <p class="text-sm text-red-500 m-0">{$t(pending.error)}</p>
      {/if}

      <div class="flex gap-3 flex-wrap">
        <button class="bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-full font-bold text-sm flex items-center gap-2 disabled:opacity-50" disabled={checking || !form.text.trim()} onclick={check}>
          <SearchIcon size={14} /> {checking ? $t('management.lineups.checking') : $t('management.lineups.check')}
        </button>
        <button class="bg-brand text-black px-4 py-2 rounded-full font-bold text-sm disabled:opacity-50" disabled={!pending.valid || saving} onclick={save}>
          {saving ? $t('common.saving') : $t('common.save')}
        </button>
      </div>

      {#if report}
        <div class="border-t border-white/10 pt-4" data-testid="lineup-report">
          <p class="text-sm font-bold m-0 mb-2">
            {$t('management.lineups.reportSummary', { matched: report.matched.length, total: report.matched.length + report.unmatched.length })}
          </p>
          {#if report.unmatched.length === 0}
            <p class="text-sm text-brand m-0 flex items-center gap-1"><Check size={14} /> {$t('management.lineups.allMatched')}</p>
          {:else}
            <ul class="list-none m-0 p-0 flex flex-col gap-2">
              {#each report.unmatched as name (name)}
                <li class="text-sm flex flex-wrap items-center gap-2">
                  <span class="text-red-400 flex items-center gap-1"><X size={14} /> {name}</span>
                  {#each report.suggestions?.[name] ?? [] as suggestion (suggestion)}
                    <button class="bg-white/10 hover:bg-brand hover:text-black rounded-full px-2 py-0.5 text-xs" onclick={() => takeSuggestion(name, suggestion)}>
                      {suggestion}
                    </button>
                  {:else}
                    <span class="text-xs text-muma-spotify-text">{$t('management.lineups.noSuggestion')}</span>
                  {/each}
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</section>
