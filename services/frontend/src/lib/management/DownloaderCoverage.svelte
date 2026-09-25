<script>
  import { t, locale, formatNumber, formatDateTime } from '../i18n/index.js';
  import { AlertTriangle, RotateCcw, ExternalLink, X } from '@lucide/svelte';
  import { linksOf, kindLabel } from './channelLinks.js';
  import { describeBackoff } from './downloaderTiming';
  import {
    filterAccounts,
    sortAccounts,
    formatPercent,
    formatAge,
    barSegments,
    reasonLabel,
    stateLabel,
    isCounted,
  } from './downloaderCoverage';

  export let API_BASE;
  export let getHeaders;
  // Opens the Koppelingen sub-tab, where a channel's open proposal is decided.
  export let onOpenLinks = () => {};
  export let onMessage = () => {};
  export let onError = () => {};

  const SOURCE_LABELS = { soundcloud: 'SoundCloud', youtube: 'YouTube' };
  // 1.100 rows of bars is fine for the browser; 1.100 rows is not fine for a
  // person. Show the top of the list and let the rest be asked for.
  const PAGE = 100;

  let source = 'soundcloud';
  let filter = 'backlog';
  let sort = 'remaining';
  let query = '';
  let limit = PAGE;

  let body = null;
  let loading = false;
  let error = '';
  // One body per source, so switching back does not refetch.
  let cache = {};

  $: load(source);
  $: visible = sortAccounts(filterAccounts(body?.accounts, filter, query), sort);
  $: shown = visible.slice(0, limit);
  // $locale is read so the label is rebuilt in the new language when it changes.
  $: backoff = ($locale, describeBackoff(body?.totals?.rate_state));

  async function load(which, force = false) {
    if (!force && cache[which]) {
      body = cache[which];
      return;
    }
    loading = true;
    error = '';
    try {
      const res = await fetch(`${API_BASE}/api/downloaders/coverage/${which}`, { headers: getHeaders() });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      cache = { ...cache, [which]: data };
      if (which === source) body = data;
    } catch (err) {
      error = err.message;
      body = null;
    } finally {
      loading = false;
    }
  }

  /** Remove a confirmed link; the proposal behind it counts as rejected from then on. */
  async function unlink(channel, kind) {
    try {
      const res = await fetch(`${API_BASE}/api/channel-links/channels/${channel.id}/${kind}`, {
        method: 'DELETE',
        headers: getHeaders(),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      onMessage($t('management.downloaders.coverage.unlinked', { channel: channel.name }));
      await load(source, true);
    } catch (err) {
      onError(err.message);
    }
  }

  function pick(which) {
    source = which;
    limit = PAGE;
  }

  function externalUrl(row) {
    if (source === 'youtube') {
      return `https://youtube.com/${row.account.startsWith('@') ? row.account : 'channel/' + row.account}`;
    }
    return `https://soundcloud.com/${row.account}`;
  }

  function toneClass(tone) {
    if (tone === 'parked') return 'text-red-400';
    if (tone === 'slowed') return 'text-yellow-400';
    if (tone === 'ok') return 'text-brand';
    return 'text-muma-spotify-text';
  }

  function n(value) {
    if (value === null || value === undefined) return '—';
    return formatNumber(value, $locale);
  }

  function when(iso) {
    if (!iso) return null;
    return formatDateTime(iso, $locale);
  }
</script>

<div class="space-y-6 animate-in fade-in duration-300">
  <p class="text-muma-spotify-text text-sm max-w-3xl">{$t('management.downloaders.coverage.help')}</p>

  <div class="flex flex-wrap items-center gap-3">
    {#each Object.entries(SOURCE_LABELS) as [key, label] (key)}
      <button
        on:click={() => pick(key)}
        class="text-sm font-bold rounded-full px-4 py-2 border transition-colors {source === key ? 'bg-brand text-black border-brand' : 'text-muma-spotify-text border-white/10 hover:text-white'}"
      >
        {label}
      </button>
    {/each}
    <button
      on:click={() => load(source, true)}
      class="flex items-center gap-2 text-sm font-bold text-muma-spotify-text hover:text-white border border-white/10 rounded-full px-4 py-2 ml-auto"
    >
      <RotateCcw size={14} /> {$t('management.downloaders.coverage.refresh')}
    </button>
  </div>

  {#if error}
    <div class="bg-red-500/10 border border-red-500/30 rounded-xl p-6 space-y-3">
      <h3 class="text-lg font-bold flex items-center gap-2 text-red-400">
        <AlertTriangle size={20} /> {$t('management.downloaders.coverage.unavailable')}
      </h3>
      <p class="text-xs font-mono text-red-300 break-all">{error}</p>
    </div>
  {:else if loading && !body}
    <p class="text-muma-spotify-text">{$t('management.downloaders.coverage.loading')}</p>
  {:else if body}
    {@const totals = body.totals}
    <div class="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-xs uppercase font-bold text-muma-spotify-text">{$t('management.downloaders.coverage.tileCounted')}</p>
        <p class="text-2xl font-extrabold mt-1">{n(totals.counted)} <span class="text-sm font-bold text-muma-spotify-text">/ {n(totals.configured)}</span></p>
        {#if totals.never_counted}
          <p class="text-xs text-muma-spotify-text mt-1">{$t('management.downloaders.coverage.tileUncounted', { count: n(totals.never_counted) })}</p>
        {/if}
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-xs uppercase font-bold text-muma-spotify-text">{$t('management.downloaders.coverage.tileComplete')}</p>
        <p class="text-2xl font-extrabold mt-1 text-brand">{n(totals.complete)}</p>
        <p class="text-xs text-muma-spotify-text mt-1">{$t('management.downloaders.coverage.tileBacklog', { count: n(totals.with_backlog) })}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-xs uppercase font-bold text-muma-spotify-text">{$t('management.downloaders.coverage.tileRemaining')}</p>
        <p class="text-2xl font-extrabold mt-1">{n(totals.remaining)}</p>
        <p class="text-xs text-muma-spotify-text mt-1">{$t('management.downloaders.coverage.tileOf', { held: n(totals.held), listed: n(totals.listed) })}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-xs uppercase font-bold text-muma-spotify-text">{$t('management.downloaders.coverage.tileExcluded')}</p>
        <p class="text-2xl font-extrabold mt-1">{n(totals.excluded)}</p>
        <p class="text-xs text-muma-spotify-text mt-1">{$t('management.downloaders.coverage.tileExcludedHelp')}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-xs uppercase font-bold text-muma-spotify-text">{$t('management.downloaders.coverage.tileRecent')}</p>
        <p class="text-2xl font-extrabold mt-1">{n(totals.downloads_7d)}</p>
        <p class="text-xs text-muma-spotify-text mt-1">{$t('management.downloaders.coverage.tileRecentMonth', { count: n(totals.downloads_30d) })}</p>
      </div>
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
        <p class="text-xs uppercase font-bold text-muma-spotify-text">{$t('management.downloaders.coverage.tileBackoff')}</p>
        <p class="text-sm font-bold mt-2 {toneClass(backoff.tone)}">{backoff.label}</p>
      </div>
    </div>

    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-4">
      <p class="text-xs uppercase font-bold text-muma-spotify-text mb-2">{$t('management.downloaders.coverage.writeOffs')}</p>
      <div class="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        {#each totals.write_offs as item (item.reason)}
          <span class={item.count ? '' : 'text-muma-spotify-text'}><span class="font-bold">{n(item.count)}</span> {reasonLabel(item.reason)}</span>
        {/each}
      </div>
      <p class="text-xs text-muma-spotify-text mt-2">{$t('management.downloaders.coverage.writeOffsHelp')}</p>
    </div>

    <div class="flex flex-wrap items-center gap-3">
      <input
        type="search"
        bind:value={query}
        placeholder={$t('management.downloaders.coverage.search')}
        aria-label={$t('management.downloaders.coverage.search')}
        class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 text-white text-sm focus:outline-none focus:border-brand"
      />
      <select bind:value={filter} aria-label={$t('management.downloaders.coverage.filter')} class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 text-white text-sm focus:outline-none focus:border-brand">
        <option value="backlog">{$t('management.downloaders.coverage.filterBacklog')}</option>
        <option value="all">{$t('management.downloaders.coverage.filterAll')}</option>
        <option value="complete">{$t('management.downloaders.coverage.filterComplete')}</option>
        <option value="uncounted">{$t('management.downloaders.coverage.filterUncounted')}</option>
      </select>
      <select bind:value={sort} aria-label={$t('management.downloaders.coverage.sort')} class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-2 text-white text-sm focus:outline-none focus:border-brand">
        <option value="remaining">{$t('management.downloaders.coverage.sortRemaining')}</option>
        <option value="coverage">{$t('management.downloaders.coverage.sortCoverage')}</option>
        <option value="name">{$t('management.downloaders.coverage.sortName')}</option>
        <option value="lastDownload">{$t('management.downloaders.coverage.sortLastDownload')}</option>
      </select>
      <span class="text-xs text-muma-spotify-text ml-auto">{$t('management.downloaders.coverage.rowCount', { shown: n(shown.length), total: n(visible.length) })}</span>
    </div>

    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
      <table class="w-full text-left">
        <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text">
          <tr>
            <th class="p-4">{$t('management.downloaders.coverage.colChannel')}</th>
            <th class="p-4 w-1/3">{$t('management.downloaders.coverage.colProgress')}</th>
            <th class="p-4 text-right">{$t('management.downloaders.coverage.colRemaining')}</th>
            <th class="p-4">{$t('management.downloaders.coverage.colLastDownload')}</th>
            <th class="p-4">{$t('management.downloaders.coverage.colCounted')}</th>
            <th class="p-4">{$t('management.downloaders.coverage.colLinked')}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-muma-spotify-panel/30">
          {#each shown as row (row.key)}
            {@const bar = barSegments(row)}
            <tr class="hover:bg-white/5 transition-colors">
              <td class="p-4 font-bold">
                <a href={externalUrl(row)} target="_blank" rel="noreferrer" class="flex items-center gap-2 hover:text-brand">
                  {row.account} <ExternalLink size={14} />
                </a>
                {#if row.download_type === 'video'}
                  <span class="text-xs font-bold uppercase px-2 py-0.5 rounded-full bg-red-500/20 text-red-400">{$t('management.downloaders.typeVideo')}</span>
                {/if}
              </td>
              <td class="p-4">
                {#if isCounted(row)}
                  <div class="flex h-2 rounded-full overflow-hidden bg-white/10" title="{n(row.held)} {$t('management.downloaders.coverage.held')} · {n(row.excluded)} {$t('management.downloaders.coverage.excluded')} · {n(row.remaining)} {$t('management.downloaders.coverage.remaining')}">
                    <div class="bg-brand" style="width: {bar.held}%"></div>
                    <div class="bg-white/30" style="width: {bar.excluded}%"></div>
                  </div>
                  <p class="text-xs text-muma-spotify-text mt-1">
                    <span class="text-white font-bold">{n(row.held)}</span> / {n(row.listed)} · {formatPercent(row.coverage)}
                    {#if row.excluded} · {n(row.excluded)} {$t('management.downloaders.coverage.excluded')}{/if}
                  </p>
                {:else}
                  <p class="text-xs text-muma-spotify-text italic">{$t('management.downloaders.coverage.uncounted')}</p>
                {/if}
              </td>
              <td class="p-4 text-right font-bold {row.remaining ? '' : 'text-muma-spotify-text'}">{n(row.remaining)}</td>
              <td class="p-4 text-sm" title={when(row.last_download_at) || ''}>
                {formatAge(row.last_download_at) ?? $t('management.downloaders.coverage.unknown')}
              </td>
              <td class="p-4 text-xs text-muma-spotify-text" title={when(row.snapshot_at) || ''}>
                {#if row.snapshot_at}
                  {formatAge(row.snapshot_at)} · {stateLabel(row.state)}
                {:else}
                  {$t('management.downloaders.coverage.uncounted')}
                {/if}
                {#if row.last_checked_at}
                  <br />{$t('management.downloaders.coverage.checked', { age: formatAge(row.last_checked_at) })}
                {/if}
              </td>
              <td class="p-4 text-sm">
                <div class="flex flex-wrap items-center gap-2">
                  {#each linksOf(row.channel) as link (link.kind)}
                    <span class="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full {link.kind === 'label' ? 'bg-white/10 text-white' : 'bg-brand/20 text-brand'}" title={kindLabel(link.kind)}>
                      {link.name}
                      <button
                        on:click={() => unlink(row.channel, link.kind)}
                        aria-label={$t('management.downloaders.coverage.unlink', { name: link.name })}
                        title={$t('management.downloaders.coverage.unlink', { name: link.name })}
                        class="opacity-60 hover:opacity-100"
                      >
                        <X size={12} />
                      </button>
                    </span>
                  {/each}
                  {#if row.channel?.open_proposals}
                    <button
                      on:click={() => onOpenLinks()}
                      class="text-xs font-bold px-2 py-0.5 rounded-full border border-brand/40 text-brand hover:bg-brand/10"
                    >
                      {$t('management.downloaders.coverage.linkProposal')}
                    </button>
                  {/if}
                </div>
              </td>
            </tr>
          {:else}
            <tr><td colspan="6" class="p-6 text-center text-muma-spotify-text">{$t('management.downloaders.coverage.empty')}</td></tr>
          {/each}
        </tbody>
      </table>
      {#if visible.length > shown.length}
        <div class="p-4 text-center border-t border-white/5">
          <button on:click={() => (limit += PAGE)} class="text-sm font-bold text-muma-spotify-text hover:text-white border border-white/10 rounded-full px-4 py-2">
            {$t('management.downloaders.coverage.showMore', { count: n(Math.min(PAGE, visible.length - shown.length)) })}
          </button>
        </div>
      {/if}
    </div>
  {/if}
</div>
