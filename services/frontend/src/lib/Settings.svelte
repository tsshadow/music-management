<script>
  import General from './settings/GeneralSettings.svelte';
  import Advanced from './settings/Advanced.svelte';
  import About from './settings/About.svelte';
  import { activeSettingsTab } from './store.js';

  // The active tab is persisted, so an account that still has one of the
  // removed admin tabs ('libraries', 'scan-settings', 'scanner', 'users')
  // stored would otherwise land on an empty screen. Those now live in the
  // management view; fall back to the first personal tab instead.
  const knownTabs = ['general', 'advanced', 'about'];
  $effect(() => {
    if (!knownTabs.includes($activeSettingsTab)) activeSettingsTab.set('general');
  });
</script>

<div class="flex flex-col h-full overflow-hidden">
  <!-- Content Area -->
  <main class="flex-1 overflow-y-auto">
    {#if $activeSettingsTab === 'advanced'}
      <Advanced />
    {:else if $activeSettingsTab === 'about'}
      <About />
    {:else}
      <General />
    {/if}
  </main>
</div>
