<script>
  import { t } from './i18n/index.js';
  import { authParams, currentTrack, playerState } from './store.js';
  import { loadFeedDetail } from './feeds.js';
  import { pressEntity, seedEntity } from './entitySeeds.js';
  import { entityCache, feedKey } from './entityLoaders.js';
  import Throbber from './loading/Throbber.svelte';
  import { startQueue } from './queue.js';
  import { feedContinuation } from './feedQueue.js';

  /**
   * One daily mix, as a compact tile: a colour or a cover, the title and subtitle MuMa already
   * computed, and a play button that starts the mix without leaving the screen it is on. Tapping
   * the tile itself opens the mix's own page (`FeedView`), where the rest of it lives.
   *
   * The play button is always visible on a touchscreen (`pointer-coarse`, issue #99): there is
   * no hover there to reveal it. With a mouse it still appears on hover or keyboard focus.
   */
  const { slug, title, subtitle = '', color = '#503750', cover = null, onopen } = $props();

  let starting = $state(false);

  /** Opens the mix's page, leaving its title and subtitle so the page's header is there at once. */
  function open() {
    seedEntity('feed', slug, { name: title, subtitle });
    onopen?.(slug);
  }

  /**
   * Queues the whole mix, in MuMa's order, and starts it -- without navigating away. The queue
   * carries the mix's continuation, so it tops itself up before it runs out (`feedQueue.js`).
   */
  async function playNow(event) {
    event.stopPropagation();
    if (starting || !$authParams) return;
    starting = true;
    try {
      // The page's own cache: a mix just opened plays without asking again, and a mix played
      // from here opens without asking again.
      const key = feedKey(slug);
      const cached = entityCache.peek(key);
      const detail = cached?.value ?? (await loadFeedDetail(slug, $authParams));
      if (!cached && detail.state !== 'error' && !detail.failedChunks) entityCache.set(key, detail);
      const { tracks, nextOffset } = detail;
      if (tracks.length === 0) return;
      startQueue(tracks, { name: title, continuation: feedContinuation(slug, nextOffset) });
      currentTrack.set(tracks[0]);
      playerState.update((s) => ({ ...s, playing: true }));
    } finally {
      starting = false;
    }
  }
</script>

<div
  role="button"
  tabindex="0"
  class="relative overflow-hidden rounded-lg w-full h-[150px] p-3 cursor-pointer flex flex-col justify-end group hover:brightness-110 active:scale-[0.98] transition"
  style={cover
    ? `background-image: url("${cover}"); background-size: cover; background-position: center;`
    : `background-color: ${color};`}
  onclick={open}
  onpointerdown={() => pressEntity('feed', { id: slug, name: title, subtitle })}
  onkeydown={(e) => e.key === 'Enter' && open()}
>
  <span class="absolute inset-0 {cover ? 'bg-black/45' : 'bg-black/20'}" aria-hidden="true"></span>
  <span class="relative z-10 text-white font-bold text-sm leading-tight line-clamp-2">{title}</span>
  {#if subtitle}
    <span class="relative z-10 text-white/70 text-[11px] truncate">{subtitle}</span>
  {/if}
  <button
    aria-label={$t('common.playAll')}
    title={$t('common.playAll')}
    class="relative z-10 self-end mt-2 w-9 h-9 pointer-coarse:w-12 pointer-coarse:h-12 bg-brand text-black border-none rounded-full flex items-center justify-center shadow-[0_8px_16px_rgba(0,0,0,0.3)] opacity-0 translate-y-2 transition-all group-hover:opacity-100 group-hover:translate-y-0 focus-visible:opacity-100 focus-visible:translate-y-0 pointer-coarse:opacity-100 pointer-coarse:translate-y-0 cursor-pointer"
    data-testid="mix-card-play"
    onclick={playNow}
  >
    {#if starting}
      <Throbber size={16} />
    {:else}
      <svg viewBox="0 0 24 24" width="18" height="18" fill="black">
        <path d="M7 6v12l10-6z"></path>
      </svg>
    {/if}
  </button>
</div>
