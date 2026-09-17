<script>
  import { t } from './i18n/index.js';
  import { platform as defaultPlatform } from './platform/index.js';
  import BrowseGrid from './BrowseGrid.svelte';
  import RecentPlacesRow from './RecentPlacesRow.svelte';

  /**
   * The content of the phone's "Bladeren" tab. The search box itself already
   * sits above this, in `TopBar`, shared with every other view; typing into
   * it opens the existing results panel as a floating overlay that covers
   * this grid, which is what "zolang er niet gezocht wordt" means here --
   * there is no second search box to keep in sync.
   *
   * The microphone is the other way into this same tab. It is offered only on
   * `platform.speech.supported`, so a browser tab -- which has no recogniser
   * and no `core/voice` behind it -- never shows a button that would only ever
   * reject.
   *
   * The advanced-search card used to open here, at the top of the grid; it now lives behind
   * the filter icon `TopBar.svelte` renders beside the search field on this tab, so the grid
   * is the first thing this screen shows again.
   */
  const { onnavigate, platform = defaultPlatform } = $props();

  const speechSupported = $derived(platform?.speech?.supported === true);
</script>

<div class="flex flex-col gap-4">
  <div class="flex items-center justify-between gap-4">
    <h2 class="text-xl font-bold m-0">{$t('mobile.browseAll')}</h2>
    {#if speechSupported}
      <button
        type="button"
        class="w-10 h-10 rounded-full flex items-center justify-center bg-[#282828] text-white border-none cursor-pointer hover:bg-[#333] shrink-0"
        onclick={() => onnavigate('voice')}
        aria-label={$t('voice.mic')}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3z"></path>
          <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.93V20H8a1 1 0 1 0 0 2h8a1 1 0 1 0 0-2h-3v-2.07A7 7 0 0 0 19 11z"></path>
        </svg>
      </button>
    {/if}
  </div>
  <RecentPlacesRow {onnavigate} />
  <BrowseGrid {onnavigate} {platform} />
</div>
