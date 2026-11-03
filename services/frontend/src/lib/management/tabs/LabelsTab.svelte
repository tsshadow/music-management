<script>
  import { format, t } from '../../i18n/index.js';
  import { onDestroy, onMount } from 'svelte';
  import { SvelteURLSearchParams } from 'svelte/reactivity';
  import { RefreshCw, Search, Pencil, Tag, ChevronLeft, ChevronRight, Inbox } from '@lucide/svelte';
  import { activeView, activeManagementTab } from '../../store.js';
  import { pageOf } from '../artistCuration.js';

  /**
   * Every label the library holds, most tracks first, with what the tagger knows about
   * it -- catalogue-id prefixes, genre rules, parent -- and the way into the edit page
   * that changes those. Where the artist page decides whether a name *is* an artist,
   * labels come from release folders and NFOs and are rarely wrong; the work here is
   * finding the ones without rules, which is what the columns are for.
   */
  let { API_BASE, getHeaders, onError } = $props();

  const PAGE_SIZE = 100;
  let rows = $state([]);
  let total = $state(0);
  let offset = $state(0);
  let loading = $state(false);
  let search = $state('');
  let searchTimer = null;

  const paging = $derived(pageOf(total, offset, PAGE_SIZE));
  const n = (value) => $format.number(value);

  function onSearchInput(event) {
    search = event.currentTarget.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      offset = 0;
      fetchRows();
    }, 250);
  }

  function turnPage(delta) {
    const next = offset + delta * PAGE_SIZE;
    if (next < 0 || next >= total) return;
    offset = next;
    fetchRows();
  }

  async function fetchRows() {
    loading = true;
    try {
      const params = new SvelteURLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
      if (search.trim()) params.set('q', search.trim());
      const res = await fetch(`${API_BASE}/api/curation/labels?${params}`, { headers: getHeaders() });
      if (res.ok) {
        const body = await res.json();
        rows = body.rows || [];
        total = body.total || 0;
      } else {
        onError($t('management.labels.loadFailed'));
      }
    } catch {
      onError($t('management.labels.loadNetworkError'));
    } finally {
      loading = false;
    }
  }

  /** The edit page is a view of the player, not a management tab: leave Management for it. */
  function edit(row) {
    activeView.set(`label-edit:${row.name}`);
  }

  function openProposals() {
    activeManagementTab.set('label-proposals');
  }

  onMount(fetchRows);
  onDestroy(() => clearTimeout(searchTimer));
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500" data-testid="labels-tab">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <Tag class="text-brand" size={32} /> {$t('management.tabs.labels')}
      </h2>
      <p class="text-muma-spotify-text">{$t('management.labels.subtitle')}</p>
    </div>
    <button class="bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded-full font-bold text-sm flex items-center gap-2" onclick={openProposals}>
      <Inbox size={16} /> {$t('management.tabs.labelProposals')}
    </button>
  </header>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
      <h3 class="text-xl font-bold">
        {$t('management.tabs.labels')}
        <span class="text-muma-spotify-text text-sm font-normal">({n(total)})</span>
      </h3>
      <div class="flex items-center gap-3">
        <div class="relative">
          <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" />
          <input
            type="text"
            value={search}
            oninput={onSearchInput}
            placeholder={$t('management.labels.searchPlaceholder')}
            aria-label={$t('management.labels.searchLabel')}
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
    {:else if rows.length === 0}
      <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
        <Tag size={48} class="mb-4 opacity-20" />
        <p>{search ? $t('management.labels.noneForSearch', { search }) : $t('management.labels.empty')}</p>
      </div>
    {:else}
      <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
              <th class="p-4">{$t('nav.labels')}</th>
              <th class="p-4">{$t('management.labels.tracks')}</th>
              <th class="p-4">{$t('management.labels.catids')}</th>
              <th class="p-4">{$t('management.labels.genreRules')}</th>
              <th class="p-4">{$t('management.labels.parent')}</th>
              <th class="p-4 text-right">{$t('management.artists.actions')}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30">
            {#each rows as row (row.id)}
              <tr class="hover:bg-white/5 transition-colors">
                <td class="p-4">
                  <div class="font-bold">{row.name}</div>
                  {#if row.mbid}
                    <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-brand/20 text-brand">MusicBrainz</span>
                  {/if}
                </td>
                <td class="p-4 text-muma-spotify-text">{n(row.track_count)}</td>
                <td class="p-4 {row.catid_count ? '' : 'text-muma-spotify-text'}">{n(row.catid_count)}</td>
                <td class="p-4 {row.genre_count ? '' : 'text-yellow-500'}">{row.genre_count ? n(row.genre_count) : $t('management.labels.noGenreRule')}</td>
                <td class="p-4 text-muma-spotify-text">{row.parent_name || '—'}</td>
                <td class="p-4 text-right">
                  <button
                    onclick={() => edit(row)}
                    aria-label={$t('management.labels.edit', { name: row.name })}
                    class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 hover:scale-105 transition-transform ml-auto"
                  >
                    <Pencil size={14} /> {$t('common.edit')}
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <div class="px-6 py-3 flex items-center justify-between text-xs text-muma-spotify-text border-t border-white/5">
        <span>{$t('management.artists.page', paging)}</span>
        <div class="flex gap-2">
          <button class="p-1 hover:text-white disabled:opacity-30" disabled={offset === 0} aria-label={$t('management.artists.previousPage')} onclick={() => turnPage(-1)}><ChevronLeft size={16} /></button>
          <button class="p-1 hover:text-white disabled:opacity-30" disabled={offset + PAGE_SIZE >= total} aria-label={$t('management.artists.nextPage')} onclick={() => turnPage(1)}><ChevronRight size={16} /></button>
        </div>
      </div>
    {/if}
  </div>
</section>
