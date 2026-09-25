<!--
  The Koppelingen sub-tab of Beheer -> Downloaders: open proposals that link a
  channel to its label or artist, with confirm and reject per row and a button
  that runs the search again. See docs/designs/channel-links/functional.md.
-->
<script>
  import { t, locale, formatNumber } from '../i18n/index.js';
  import { onMount } from 'svelte';
  import { Check, X, RotateCcw, Search, Link2, AlertTriangle } from '@lucide/svelte';
  import { filterProposals, countByKind, kindLabel, sourceLabel, refreshMessage, PLATFORMS } from './channelLinks.js';

  let { API_BASE, getHeaders, onMessage = () => {}, onError = () => {} } = $props();

  const PLATFORM_LABELS = { soundcloud: 'SoundCloud', youtube: 'YouTube' };

  let proposals = $state([]);
  let loading = $state(false);
  let busy = $state(false);
  let error = $state('');
  let kind = $state('');
  let platform = $state('');
  let query = $state('');

  const visible = $derived(filterProposals(proposals, { kind, platform, query }));
  const counts = $derived(countByKind(proposals));

  /** The API's own explanation when it gave one, so an outage is more than a status code. */
  async function reasonFor(res) {
    const detail = await res.json().catch(() => ({}));
    return detail.detail || `HTTP ${res.status}`;
  }

  async function load() {
    loading = true;
    error = '';
    try {
      const res = await fetch(`${API_BASE}/api/channel-links/proposals?status=new`, { headers: getHeaders() });
      if (!res.ok) throw new Error(await reasonFor(res));
      proposals = await res.json();
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const res = await fetch(`${API_BASE}/api/channel-links/proposals/refresh`, { method: 'POST', headers: getHeaders() });
      if (!res.ok) throw new Error(await reasonFor(res));
      onMessage(refreshMessage(await res.json()));
      await load();
    } catch (e) {
      onError(e.message);
    } finally {
      busy = false;
    }
  }

  /** Confirm or reject one proposal; the row leaves the list either way. */
  async function decide(proposal, action) {
    if (busy) return;
    busy = true;
    try {
      const res = await fetch(`${API_BASE}/api/channel-links/proposals/${proposal.id}/${action}`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (!res.ok) throw new Error(await reasonFor(res));
      const body = await res.json();
      if (body.status === 'stale') onMessage($t('management.downloaders.links.stale'));
      else if (action === 'confirm') onMessage($t('management.downloaders.links.confirmed', { channel: proposal.channel_name, target: proposal.target_name }));
      else onMessage($t('management.downloaders.links.rejected'));
      proposals = proposals.filter((row) => row.id !== proposal.id);
    } catch (e) {
      onError(e.message);
    } finally {
      busy = false;
    }
  }

  function n(value) {
    return formatNumber(value ?? 0, $locale);
  }

  onMount(load);
</script>

<div class="space-y-6 animate-in fade-in duration-300">
  <p class="text-muma-spotify-text text-sm max-w-3xl">{$t('management.downloaders.links.help')}</p>

  <div class="flex flex-wrap items-center gap-3">
    <input
      type="search"
      bind:value={query}
      placeholder={$t('management.downloaders.links.search')}
      aria-label={$t('management.downloaders.links.search')}
      class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 text-white text-sm focus:outline-none focus:border-brand"
    />
    <select bind:value={kind} aria-label={$t('management.downloaders.links.kindFilter')} class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 text-white text-sm focus:outline-none focus:border-brand">
      <option value="">{$t('management.downloaders.links.allKinds')}</option>
      <option value="label">{kindLabel('label')} ({n(counts.label)})</option>
      <option value="artist">{kindLabel('artist')} ({n(counts.artist)})</option>
    </select>
    <select bind:value={platform} aria-label={$t('management.downloaders.links.platformFilter')} class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 text-white text-sm focus:outline-none focus:border-brand">
      <option value="">{$t('management.downloaders.links.allPlatforms')}</option>
      {#each PLATFORMS as key (key)}
        <option value={key}>{PLATFORM_LABELS[key]}</option>
      {/each}
    </select>
    <button
      onclick={refresh}
      disabled={busy}
      class="flex items-center gap-2 text-sm font-bold bg-brand text-black rounded-full px-4 py-2 ml-auto transition-transform hover:scale-105 disabled:opacity-50 disabled:hover:scale-100"
    >
      <Search size={14} /> {$t('management.downloaders.links.refresh')}
    </button>
    <button
      onclick={load}
      disabled={loading}
      aria-label={$t('common.refresh')}
      class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
    >
      <RotateCcw size={16} class={loading ? 'animate-spin' : ''} />
    </button>
  </div>

  {#if error}
    <div class="bg-red-500/10 border border-red-500/30 rounded-xl p-6 space-y-3">
      <h3 class="text-lg font-bold flex items-center gap-2 text-red-400">
        <AlertTriangle size={20} /> {$t('management.downloaders.links.unavailable')}
      </h3>
      <p class="text-xs font-mono text-red-300 break-all">{error}</p>
    </div>
  {:else if loading && proposals.length === 0}
    <p class="text-muma-spotify-text">{$t('management.downloaders.links.loading')}</p>
  {:else if proposals.length === 0}
    <div class="flex flex-col items-center justify-center p-16 text-muma-spotify-text">
      <Link2 size={48} class="mb-4 opacity-20" />
      <p>{$t('management.downloaders.links.empty')}</p>
    </div>
  {:else}
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
      <table class="w-full text-left text-sm">
        <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text">
          <tr>
            <th class="p-4">{$t('management.downloaders.links.colChannel')}</th>
            <th class="p-4">{$t('management.downloaders.links.colTarget')}</th>
            <th class="p-4">{$t('management.downloaders.links.colSource')}</th>
            <th class="p-4 text-right">{$t('management.downloaders.links.colTracks')}</th>
            <th class="p-4 text-right">{$t('management.genres.actions')}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-muma-spotify-panel/30">
          {#each visible as proposal (proposal.id)}
            <tr class="hover:bg-white/5 transition-colors">
              <td class="p-4 font-bold">
                {proposal.channel_name}
                <span class="block text-xs font-normal text-muma-spotify-text">{PLATFORM_LABELS[proposal.platform] ?? proposal.platform}</span>
              </td>
              <td class="p-4">
                {proposal.target_name}
                <span class="ml-2 text-xs font-bold uppercase px-2 py-0.5 rounded-full {proposal.kind === 'label' ? 'bg-white/10 text-white' : 'bg-brand/20 text-brand'}">{kindLabel(proposal.kind)}</span>
              </td>
              <td class="p-4 text-xs text-muma-spotify-text">{sourceLabel(proposal.source)}</td>
              <td class="p-4 text-right tabular-nums">{n(proposal.track_count)}</td>
              <td class="p-4 text-right whitespace-nowrap">
                <button
                  onclick={() => decide(proposal, 'confirm')}
                  disabled={busy}
                  class="bg-brand text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 inline-flex items-center gap-1"
                >
                  <Check size={14} /> {$t('management.downloaders.links.confirm')}
                </button>
                <button
                  onclick={() => decide(proposal, 'reject')}
                  disabled={busy}
                  class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 inline-flex items-center gap-1 ml-2"
                >
                  <X size={14} /> {$t('management.downloaders.links.reject')}
                </button>
              </td>
            </tr>
          {:else}
            <tr><td colspan="5" class="p-6 text-center text-muma-spotify-text">{$t('management.downloaders.links.noMatch')}</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
