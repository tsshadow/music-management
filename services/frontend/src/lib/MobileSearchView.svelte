<script>
  import { t } from './i18n/index.js';
  import BrowseGrid from './BrowseGrid.svelte';

  /**
   * The content of the phone's "Zoeken" tab. The search box itself already
   * sits above this, in `TopBar`, shared with every other view; typing into
   * it opens the existing results panel as a floating overlay that covers
   * this grid, which is what "zolang er niet gezocht wordt" means here --
   * there is no second search box to keep in sync.
   */
  const { onnavigate } = $props();
</script>

<div class="flex flex-col gap-4">
  <h2 class="text-xl font-bold m-0">{$t('mobile.browseAll')}</h2>
  <BrowseGrid {onnavigate} />
</div>
