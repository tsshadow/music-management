<script>
  /**
   * The tagger itself: force a full rescan, run the retag that rule changes have
   * queued up, and cut a running round short. The rules the tagger reads -- which
   * genre an artist or a label implies, which genres exist at all -- moved to
   * Curatie › Genres, where each rule table has its own panel; this page only points
   * there.
   */
  import { onMount, onDestroy } from 'svelte';
  import { t } from '../../i18n/index.js';
  import { ListChecks, Square, RotateCcw } from '@lucide/svelte';
  import { activeManagementTab } from '../../store.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  // What a rule change has queued up, and whether the tagger is at it. Shown before the
  // button is pressed, because a wide match can touch more files than intended and the
  // count is the only brake; polled while the page is open, because watching it go down
  // is the only way to see that a restart reached the queue.
  let retagPending = $state({ total: 0, by_reason: [], busy: false, stopping: false });

  const POLL_MS = 5000;
  let pollTimer = null;

  async function fetchRetagPending() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/retag/pending`, { headers: getHeaders() });
      if (res.ok) retagPending = { busy: false, stopping: false, ...(await res.json()) };
    } catch {
      // Silent: the block simply stays hidden when the count cannot be fetched.
    }
  }

  onMount(() => {
    fetchRetagPending();
    pollTimer = setInterval(fetchRetagPending, POLL_MS);
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  async function startRetag() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/retag/run`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.retagStarted'));
        retagPending.busy = true;
      } else if (res.status === 409) {
        onError($t('management.tagger.retagBusy'));
      }
    } catch {
      onError($t('management.tagger.retagFailed'));
    }
    fetchRetagPending();
  }

  async function stopTagger() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/tag/stop`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.stopRequested'));
        retagPending.stopping = true;
      }
    } catch {
      onError($t('management.tagger.stopFailed'));
    }
    fetchRetagPending();
  }

  async function restartTagger() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/retag/restart`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.restartRequested'));
        retagPending.stopping = true;
      }
    } catch {
      onError($t('management.tagger.restartFailed'));
    }
    fetchRetagPending();
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

  {#if retagPending.total > 0 || retagPending.busy}
    <div
      data-testid="retag-pending"
      class="bg-muma-spotify-panel p-4 rounded-xl border border-brand/40 flex items-center justify-between gap-4 flex-wrap"
    >
      <div class="text-sm space-y-1">
        {#if retagPending.total > 0}
          <p class="m-0">
            <span class="font-bold">{retagPending.total}</span>
            {$t('management.tagger.retagPending')}
            <span class="text-muma-spotify-text">
              {retagPending.by_reason.map((r) => `${r.reason} (${r.count})`).join(', ')}
            </span>
          </p>
        {/if}
        {#if retagPending.stopping}
          <p class="m-0 text-muma-spotify-text" data-testid="tagger-state">{$t('management.tagger.stateStopping')}</p>
        {:else if retagPending.busy}
          <p class="m-0 text-muma-spotify-text" data-testid="tagger-state">{$t('management.tagger.stateBusy')}</p>
        {/if}
      </div>
      <div class="flex items-center gap-2">
        {#if retagPending.busy}
          <button
            onclick={stopTagger}
            disabled={retagPending.stopping}
            class="bg-white/10 text-white text-xs font-bold px-4 py-2 rounded-full hover:bg-white/20 transition-colors whitespace-nowrap disabled:opacity-50 flex items-center gap-1"
          >
            <Square size={12} /> {$t('management.tagger.stop')}
          </button>
          <button
            onclick={restartTagger}
            disabled={retagPending.stopping}
            class="bg-brand text-black text-xs font-bold px-4 py-2 rounded-full hover:bg-white transition-colors whitespace-nowrap disabled:opacity-50 flex items-center gap-1"
          >
            <RotateCcw size={12} /> {$t('management.tagger.restart')}
          </button>
        {:else}
          <button
            onclick={startRetag}
            class="bg-brand text-black text-xs font-bold px-4 py-2 rounded-full hover:bg-white transition-colors whitespace-nowrap"
          >
            {$t('management.tagger.retagNow')}
          </button>
        {/if}
      </div>
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
