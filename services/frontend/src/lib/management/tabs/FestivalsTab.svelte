<script>
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { RefreshCw, Search, Plus, Pencil, Trash2, Tent, FlaskConical, X } from '@lucide/svelte';
  import { buildFestival, emptyFestival, filterFestivals, formFrom } from '../festivals.js';

  /**
   * The festivals the tagger recognises: canonical name, the spellings it occurs under,
   * and the date per edition. One row per festival with all three, a form to change
   * them, and a probe box that runs the real matcher over a piece of text so an alias
   * can be checked before it is saved rather than after the next tagger run.
   */
  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let rows = $state([]);
  let loading = $state(false);
  let search = $state('');
  let form = $state(null);
  let saving = $state(false);
  let probeText = $state('');
  let probeResult = $state(null);

  const visible = $derived(filterFestivals(rows, search));
  const pending = $derived(form ? buildFestival(form) : { valid: false, error: null });

  async function fetchRows() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/rules/festivals`, { headers: getHeaders() });
      if (res.ok) rows = await res.json();
      else onError($t('management.festivals.loadFailed'));
    } catch {
      onError($t('management.festivals.loadNetworkError'));
    } finally {
      loading = false;
    }
  }

  function openNew() {
    form = formFrom(emptyFestival());
  }

  function openEdit(row) {
    form = formFrom(row);
  }

  function addEdition() {
    form.editions = [...form.editions, { year: '', date: '' }];
  }

  function removeEdition(index) {
    form.editions = form.editions.filter((_, i) => i !== index);
  }

  async function save() {
    if (!pending.valid) {
      onError($t(pending.error));
      return;
    }
    saving = true;
    try {
      const url = form.id ? `${API_BASE}/api/rules/festivals/${form.id}` : `${API_BASE}/api/rules/festivals`;
      const res = await fetch(url, {
        method: form.id ? 'PUT' : 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(pending.payload)
      });
      if (res.ok) {
        onMessage($t('management.festivals.saved', { name: pending.payload.name }));
        form = null;
        await fetchRows();
      } else {
        const data = await res.json().catch(() => ({}));
        onError(data.detail || $t('management.festivals.saveFailed'));
      }
    } catch {
      onError($t('management.festivals.saveNetworkError'));
    } finally {
      saving = false;
    }
  }

  async function remove(row) {
    if (!confirm($t('management.festivals.confirmDelete', { name: row.name }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/festivals/${row.id}`, { method: 'DELETE', headers: getHeaders() });
      if (res.ok) {
        onMessage($t('management.festivals.deleted', { name: row.name }));
        await fetchRows();
      } else {
        const data = await res.json().catch(() => ({}));
        onError(data.detail || $t('management.festivals.saveFailed'));
      }
    } catch {
      onError($t('management.festivals.saveNetworkError'));
    }
  }

  async function probe() {
    if (!probeText.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/festivals/probe`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ text: probeText })
      });
      if (res.ok) probeResult = (await res.json()).matches || [];
      else onError($t('management.festivals.loadFailed'));
    } catch {
      onError($t('management.festivals.loadNetworkError'));
    }
  }

  onMount(fetchRows);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500" data-testid="festivals-tab">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <Tent class="text-brand" size={32} /> {$t('management.tabs.festivals')}
      </h2>
      <p class="text-muma-spotify-text">{$t('management.festivals.subtitle')}</p>
    </div>
    <button
      class="bg-brand text-black px-4 py-2 rounded-full font-bold text-sm flex items-center gap-2 hover:scale-105 transition-transform"
      onclick={openNew}
    >
      <Plus size={16} /> {$t('management.festivals.new')}
    </button>
  </header>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-6 flex flex-col gap-3" data-testid="festival-probe">
    <h3 class="text-lg font-bold flex items-center gap-2"><FlaskConical size={18} class="text-brand" /> {$t('management.festivals.probeTitle')}</h3>
    <p class="text-sm text-muma-spotify-text m-0">{$t('management.festivals.probeHelp')}</p>
    <div class="flex gap-2 flex-wrap">
      <input
        type="text"
        bind:value={probeText}
        placeholder={$t('management.festivals.probePlaceholder')}
        aria-label={$t('management.festivals.probeTitle')}
        class="flex-1 min-w-[240px] bg-muma-spotify-dark border border-muma-spotify-panel rounded-full px-4 py-2 text-sm focus:outline-none focus:border-brand"
        onkeydown={(e) => e.key === 'Enter' && probe()}
      />
      <button class="bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-full font-bold text-sm" onclick={probe}>
        {$t('management.festivals.probeRun')}
      </button>
    </div>
    {#if probeResult}
      <p class="text-sm m-0" data-testid="probe-result">
        {#if probeResult.length === 0}
          <span class="text-muma-spotify-text">{$t('management.festivals.probeNone')}</span>
        {:else}
          {#each probeResult as match, i (i)}
            <span class="inline-block bg-brand/20 text-brand rounded-full px-3 py-1 mr-2 font-bold">
              {match.festival}{#if match.year} · {match.year}{/if}{#if match.date} · {match.date}{/if}
            </span>
          {/each}
        {/if}
      </p>
    {/if}
  </div>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
      <h3 class="text-xl font-bold">
        {$t('management.tabs.festivals')}
        <span class="text-muma-spotify-text text-sm font-normal">({rows.length})</span>
      </h3>
      <div class="flex items-center gap-3">
        <div class="relative">
          <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" />
          <input
            type="text"
            bind:value={search}
            placeholder={$t('management.festivals.searchPlaceholder')}
            aria-label={$t('management.festivals.searchLabel')}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-brand"
          />
        </div>
        <button onclick={fetchRows} disabled={loading} aria-label={$t('common.refresh')} class="text-muma-spotify-text hover:text-white disabled:opacity-50">
          <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
        </button>
      </div>
    </div>

    {#if loading && rows.length === 0}
      <div class="flex items-center justify-center p-20"><RefreshCw class="animate-spin text-brand" size={32} /></div>
    {:else if visible.length === 0}
      <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
        <Tent size={48} class="mb-4 opacity-20" />
        <p>{search ? $t('management.festivals.noneForSearch', { search }) : $t('management.festivals.empty')}</p>
      </div>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
              <th class="p-4">{$t('management.festivals.name')}</th>
              <th class="p-4">{$t('management.festivals.aliases')}</th>
              <th class="p-4">{$t('management.festivals.editions')}</th>
              <th class="p-4 text-right">{$t('management.artists.actions')}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30">
            {#each visible as row (row.id)}
              <tr class="hover:bg-white/5 transition-colors {row.active ? '' : 'opacity-50'}">
                <td class="p-4">
                  <div class="font-bold">{row.name}</div>
                  {#if !row.active}
                    <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-white/10 text-muma-spotify-text">{$t('management.festivals.inactive')}</span>
                  {/if}
                </td>
                <td class="p-4">
                  <div class="flex flex-wrap gap-1">
                    {#each row.aliases as alias (alias)}
                      <span class="bg-white/10 rounded-full px-2 py-0.5 text-xs">{alias}</span>
                    {:else}
                      <span class="text-muma-spotify-text text-xs">{$t('management.festivals.nameOnly')}</span>
                    {/each}
                  </div>
                </td>
                <td class="p-4 text-muma-spotify-text text-xs">
                  {#each row.editions as edition (edition.year)}
                    <div>{edition.year} · {edition.date}</div>
                  {:else}
                    <span>—</span>
                  {/each}
                </td>
                <td class="p-4 text-right">
                  <div class="flex justify-end gap-2">
                    <button
                      onclick={() => openEdit(row)}
                      aria-label={$t('management.festivals.edit', { name: row.name })}
                      class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 hover:scale-105 transition-transform"
                    >
                      <Pencil size={14} /> {$t('common.edit')}
                    </button>
                    <button
                      onclick={() => remove(row)}
                      aria-label={$t('management.festivals.delete', { name: row.name })}
                      class="bg-red-500/10 text-red-400 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1"
                    >
                      <Trash2 size={14} />
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
</section>

{#if form}
  <div class="fixed inset-0 bg-black/80 flex items-center justify-center z-[1100] animate-in fade-in duration-200 p-4">
    <div class="bg-[#282828] p-8 rounded-xl border border-white/10 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto" data-testid="festival-form">
      <h3 class="text-2xl font-bold mb-6 flex items-center gap-2">
        <Tent class="text-brand" /> {form.id ? $t('management.festivals.editTitle') : $t('management.festivals.new')}
      </h3>

      <label class="block mb-4">
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.festivals.name')}</span>
        <input type="text" bind:value={form.name} class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand" />
      </label>

      <label class="flex items-center gap-3 mb-4 cursor-pointer">
        <input type="checkbox" bind:checked={form.active} class="accent-brand w-4 h-4" />
        <span class="text-sm">{$t('management.festivals.activeHelp')}</span>
      </label>

      <label class="block mb-4">
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.festivals.aliases')}</span>
        <p class="text-xs text-muma-spotify-text m-0 mb-1">{$t('management.festivals.aliasesHelp')}</p>
        <textarea bind:value={form.aliasText} rows="4" class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand font-mono"></textarea>
      </label>

      <div class="mb-6">
        <span class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">{$t('management.festivals.editions')}</span>
        <p class="text-xs text-muma-spotify-text m-0 mb-2">{$t('management.festivals.editionsHelp')}</p>
        {#each form.editions as edition, i (i)}
          <div class="flex gap-2 mb-2 items-center">
            <input type="number" bind:value={edition.year} placeholder="2025" aria-label={$t('management.festivals.year')} class="w-24 bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand" />
            <input type="date" bind:value={edition.date} aria-label={$t('management.festivals.date')} class="flex-1 bg-muma-spotify-dark border border-muma-spotify-panel rounded-md px-3 py-2 text-sm focus:outline-none focus:border-brand" />
            <button type="button" onclick={() => removeEdition(i)} aria-label={$t('management.festivals.removeEdition')} class="text-muma-spotify-text hover:text-white"><X size={16} /></button>
          </div>
        {/each}
        <button type="button" onclick={addEdition} class="text-xs font-bold text-brand hover:underline flex items-center gap-1"><Plus size={12} /> {$t('management.festivals.addEdition')}</button>
      </div>

      {#if pending.error}
        <p class="text-sm text-red-500 mb-4">{$t(pending.error)}</p>
      {/if}

      <div class="flex gap-4">
        <button class="flex-1 py-3 rounded-full font-bold bg-brand text-black hover:scale-105 transition-all disabled:opacity-50 disabled:hover:scale-100" disabled={!pending.valid || saving} onclick={save}>
          {saving ? $t('common.saving') : $t('common.save')}
        </button>
        <button class="flex-1 py-3 rounded-full font-bold bg-white/10 text-white hover:bg-white/20 transition-all" onclick={() => (form = null)}>
          {$t('common.cancel')}
        </button>
      </div>
    </div>
  </div>
{/if}
