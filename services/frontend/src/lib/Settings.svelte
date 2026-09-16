<script>
  import General from './settings/GeneralSettings.svelte';
  import Advanced from './settings/Advanced.svelte';
  import About from './settings/About.svelte';
  import DeviceSettings from './settings/DeviceSettings.svelte';
  import Help from './settings/Help.svelte';
  import { activeSettingsTab, activeView } from './store.js';
  import { SETTINGS_TABS } from './router.js';
  import { platform } from './platform/index.js';

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
</script>

<div class="flex flex-col h-full overflow-hidden">
  <!-- Content Area -->
  <main class="flex-1 overflow-y-auto">
    {#if $activeSettingsTab === 'advanced'}
      <Advanced />
    {:else if $activeSettingsTab === 'about'}
      <About />
    {:else if $activeSettingsTab === 'device' && platform.system.isNative}
      <DeviceSettings />
    {:else if $activeSettingsTab === 'help'}
      <Help {onnavigate} />
    {:else}
      <General />
    {/if}
  </main>
</div>
