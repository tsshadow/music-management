<script>
  import { viewMode } from './store.js';
  import { t } from './i18n/index.js';

  /**
   * The Songs/Sets segmented control shown in the phone's top bar, next to the
   * search field and the profile button.
   *
   * Unlike the old bottom-bar tabs it replaces, tapping a segment never
   * navigates: it only sets `viewMode`, exactly like the desktop sidebar's own
   * toggle (`Sidebar.svelte`), so the mode follows the listener across
   * whichever of the three phone tabs they are standing on rather than
   * jumping them to the songs or sets view.
   *
   * Both words stay on screen -- no icon, no abbreviation, no active-word-only
   * pill -- one compact pill container holding both segments so it reads on a
   * single line next to search and the profile button.
   */
</script>

<div
  class="flex shrink-0 rounded-full border border-white/10 p-0.5 text-xs font-bold min-h-11"
  role="group"
  aria-label={$t('sidebar.toggleMode')}
>
  <button
    type="button"
    class="px-2.5 py-1.5 rounded-full border-none cursor-pointer transition-colors {$viewMode === 'songs' ? 'bg-brand-green text-black' : 'text-white/60'}"
    onclick={() => viewMode.set('songs')}
    aria-pressed={$viewMode === 'songs'}
  >
    {$t('nav.songs')}
  </button>
  <button
    type="button"
    class="px-2.5 py-1.5 rounded-full border-none cursor-pointer transition-colors {$viewMode === 'sets' ? 'bg-brand-blue text-black' : 'text-white/60'}"
    onclick={() => viewMode.set('sets')}
    aria-pressed={$viewMode === 'sets'}
  >
    {$t('nav.sets')}
  </button>
</div>
