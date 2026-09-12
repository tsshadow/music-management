<script>
  import { viewMode } from './store.js';
  import { t } from './i18n/index.js';

  /**
   * The Songs/Sets pill switch shown above Home, Search and Library on the
   * phone -- Spotify's "Music / Podcasts & Shows" pattern.
   *
   * Unlike the old bottom-bar tabs it replaces, tapping a chip never
   * navigates: it only sets `viewMode`, exactly like the desktop sidebar's own
   * toggle (`Sidebar.svelte`), so the mode follows the listener across
   * whichever of the three phone tabs they are standing on rather than
   * jumping them to the songs or sets view.
   */
</script>

<div class="flex gap-2" role="group" aria-label={$t('sidebar.toggleMode')}>
  <button
    type="button"
    class="px-4 py-1.5 rounded-full text-sm font-bold border-none cursor-pointer transition-colors {$viewMode === 'songs' ? 'bg-brand-green text-black' : 'bg-[#282828] text-white'}"
    onclick={() => viewMode.set('songs')}
    aria-pressed={$viewMode === 'songs'}
  >
    {$t('nav.songs')}
  </button>
  <button
    type="button"
    class="px-4 py-1.5 rounded-full text-sm font-bold border-none cursor-pointer transition-colors {$viewMode === 'sets' ? 'bg-brand-blue text-black' : 'bg-[#282828] text-white'}"
    onclick={() => viewMode.set('sets')}
    aria-pressed={$viewMode === 'sets'}
  >
    {$t('nav.sets')}
  </button>
</div>
