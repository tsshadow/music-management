<script>
  import { t } from './i18n/index.js';
  import { currentTrack, playerState, authParams, isMobile, restUrl } from './store.js';
  import ArtistList from './ArtistList.svelte';

  const { track, onnavigate } = $props();

  /**
   * Starts playback of the current track.
   */
  function play() {
    currentTrack.set(track);
    playerState.update(s => ({ ...s, playing: true }));
  }

  const coverUrl = $derived(track.coverArt ? restUrl(`/rest/getCoverArt?id=${track.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg');
</script>

<div
  role="button"
  tabindex="0"
  class="bg-[#181818] rounded-lg transition-colors cursor-pointer flex flex-col group hover:bg-[#282828] {$isMobile ? 'p-2 gap-1.5' : 'p-4 gap-3'}"
  onclick={play}
  onkeydown={(e) => e.key === 'Enter' && play()}
>
  <div class="relative aspect-square shadow-[0_8px_24px_rgba(0,0,0,0.5)] rounded overflow-hidden">
    <img
      src={coverUrl}
      alt={track.title}
      class="w-full h-full object-cover"
      onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
    />
    <button
      aria-label={$t('common.play')}
      class="absolute right-2 bottom-2 w-12 h-12 bg-brand border-none rounded-full flex items-center justify-center shadow-[0_8px_16px_rgba(0,0,0,0.3)] opacity-0 translate-y-2 transition-all group-hover:opacity-100 group-hover:translate-y-0"
      onclick={(e) => { e.stopPropagation(); play(); }}
    >
      <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
        <path d="M7 6v12l10-6z"></path>
      </svg>
    </button>
  </div>
  <div class="flex flex-col min-w-0">
    <span class="text-base font-bold whitespace-nowrap overflow-hidden text-ellipsis">{track.title || track.name}</span>
    <div class="truncate">
      <ArtistList artist={track.artist} artistId={track.artistId} artists={track.artists} onnavigate={onnavigate} />
    </div>
  </div>
</div>

<style>
</style>
