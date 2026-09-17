<script>
  import { t } from './i18n/index.js';
  import { authParams, currentTrack, playerState } from './store.js';
  import { loadFeed } from './feeds.js';
  import { startQueue } from './queue.js';

  /**
   * One daily mix, as a compact tile: a colour or a cover, the title and subtitle MuMa already
   * computed, and a play button that starts the mix without leaving the screen it is on. Tapping
   * the tile itself opens the mix's own page (`FeedView`), where the rest of it lives.
   */
  const { slug, title, subtitle = '', color = '#503750', cover = null, onopen } = $props();

  let starting = $state(false);

  function open() {
    onopen?.(slug);
  }

  /** Queues the whole mix, in MuMa's order, and starts it -- without navigating away. */
  async function playNow(event) {
    event.stopPropagation();
    if (starting || !$authParams) return;
    starting = true;
    try {
      const tracks = await loadFeed(slug, $authParams);
      if (tracks.length === 0) return;
      startQueue(tracks, { name: title });
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
    class="relative z-10 self-end mt-2 w-9 h-9 bg-brand border-none rounded-full flex items-center justify-center shadow-[0_8px_16px_rgba(0,0,0,0.3)] opacity-0 translate-y-2 transition-all group-hover:opacity-100 group-hover:translate-y-0 cursor-pointer"
    onclick={playNow}
  >
    <svg viewBox="0 0 24 24" width="18" height="18" fill="black">
      <path d="M7 6v12l10-6z"></path>
    </svg>
  </button>
</div>
