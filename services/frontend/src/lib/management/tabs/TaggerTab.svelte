<script>
  /**
   * The tagger itself: force a full rescan, and run the retag that rule changes
   * have queued up. The rules the tagger reads -- which genre an artist or a label
   * implies, which genres exist at all -- moved to Curatie › Genres, where each rule
   * table has its own panel; this page only points there.
   */
  import { onMount } from 'svelte';
  import { t } from '../../i18n/index.js';
  import { ListChecks } from '@lucide/svelte';
  import { activeManagementTab } from '../../store.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  // What a rule change has queued up. Shown before the button is pressed, because a
  // wide match can touch more files than intended and the count is the only brake.
  let retagPending = $state({ total: 0, by_reason: [] });

  async function fetchRetagPending() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/retag/pending`, { headers: getHeaders() });
      if (res.ok) retagPending = await res.json();
    } catch {
      // Silent: the block simply stays hidden when the count cannot be fetched.
    }
  }

  onMount(fetchRetagPending);

  async function startRetag() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/retag/run`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.retagStarted'));
        retagPending = { total: 0, by_reason: [] };
      } else if (res.status === 409) {
        onError($t('management.tagger.retagBusy'));
      }
    } catch {
      onError($t('management.tagger.retagFailed'));
    }
  }

  async function triggerRescan() {
    if (!confirm($t('management.tagger.confirmRescan'))) return;
    try {
      const res = await fetch(`${API_BASE}/api/tagger/rescan`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.rescanTriggered'));
      }
    } catch {
      onError($t('management.tagger.rescanFailed'));
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">{$t('management.tagger.title')}</h1>
      <p class="text-muma-spotify-text text-lg">{$t('management.tagger.subtitle')}</p>
    </div>
    <div class="pb-2">
      <button
        onclick={triggerRescan}
        class="bg-white text-black text-xs font-bold px-4 py-2 rounded-full hover:bg-white/80 transition-colors"
      >
        {$t('management.tagger.forceRescan')}
      </button>
    </div>
  </header>

  {#if retagPending.total > 0}
    <div
      data-testid="retag-pending"
      class="bg-muma-spotify-panel p-4 rounded-xl border border-brand/40 flex items-center justify-between gap-4"
    >
      <p class="text-sm">
        <span class="font-bold">{retagPending.total}</span>
        {$t('management.tagger.retagPending')}
        <span class="text-muma-spotify-text">
          {retagPending.by_reason.map((r) => `${r.reason} (${r.count})`).join(', ')}
        </span>
      </p>
      <button
        onclick={startRetag}
        class="bg-brand text-black text-xs font-bold px-4 py-2 rounded-full hover:bg-white transition-colors whitespace-nowrap"
      >
        {$t('management.tagger.retagNow')}
      </button>
    </div>
  {/if}

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-6 flex items-center justify-between gap-4 flex-wrap">
    <div>
      <h3 class="text-xl font-bold flex items-center gap-2 m-0">
        <ListChecks size={20} class="text-brand" /> {$t('management.tagger.rulesMovedTitle')}
      </h3>
      <p class="text-muma-spotify-text text-sm mt-1 mb-0">{$t('management.tagger.rulesMoved')}</p>
    </div>
    <button
      onclick={() => activeManagementTab.set('genre-curation')}
      class="bg-white/10 text-white px-4 py-2 rounded-full font-bold text-xs hover:bg-white/20 transition-colors whitespace-nowrap"
    >
      {$t('management.tagger.rulesMovedLink')}
    </button>
  </div>
</section>
