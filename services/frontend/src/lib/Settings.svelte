<script>
  /**
   * The personal settings page: renders the active tab, each of which is its own chunk
   * (`settingsTabs` in lazyViews.js, issue #119). Opening settings fetches the tab on screen
   * only; while it is on its way `SettingsTabSkeleton` stands in with the tab's geometry, and
   * the next tab in the sidebar is fetched on idle so switching to it rarely waits.
   */
  import { untrack } from 'svelte';
  import { activeSettingsTab, activeView } from './store.js';
  import { SETTINGS_TABS } from './router.js';
  import LazyView from './LazyView.svelte';
  import SettingsTabSkeleton from './settings/SettingsTabSkeleton.svelte';
  import { nextSettingsTab, preloadOnIdle, settingsTabName, settingsTabs } from './lazyViews.js';

  // Only the manual navigates: its "go there" buttons open the view a section is about,
  // and the tour it can start is a view too. Dashboard passes App's own handler.
  const { onnavigate = (view) => activeView.set(view) } = $props();

  // The active tab is persisted and can also arrive from the URL, so an
  // account that still has one of the removed admin tabs ('libraries',
  // 'scan-settings', 'scanner', 'users') stored would otherwise land on an
  // empty screen. Those now live in the management view; fall back to the
  // first personal tab instead.
  $effect(() => {
    if (!SETTINGS_TABS.includes($activeSettingsTab)) activeSettingsTab.set('general');
  });

  // `device` outside the shell, or a name the effect above has not replaced yet, shows General.
  const tab = $derived(settingsTabName($activeSettingsTab));

  // Once the tab on screen is in, fetch the one after it in the sidebar when the page is idle:
  // that is where a listener browsing their settings goes next.
  $effect(() => {
    const current = tab;
    untrack(() => {
      settingsTabs
        .load(current)
        .catch(() => null)
        .then(() => {
          const next = nextSettingsTab(current);
          if (next && !settingsTabs.peek(next)) preloadOnIdle([[settingsTabs, next]]);
        });
    });
  });
</script>

<div class="flex flex-col h-full overflow-hidden">
  <!-- Content Area -->
  <main class="flex-1 overflow-y-auto">
    <LazyView registry={settingsTabs} name={tab} props={tab === 'help' ? { onnavigate } : {}}>
      {#snippet placeholder()}
        <SettingsTabSkeleton />
      {/snippet}
    </LazyView>
  </main>
</div>
