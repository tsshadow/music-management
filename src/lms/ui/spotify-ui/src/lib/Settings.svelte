<script>
  import Libraries from './settings/Libraries.svelte';
  import ScanSettings from './settings/ScanSettings.svelte';
  import Scanner from './settings/Scanner.svelte';
  import Users from './settings/Users.svelte';
  import Advanced from './settings/Advanced.svelte';
  import About from './settings/About.svelte';
  import { activeSettingsTab } from './store.js';
</script>

<div class="flex flex-col h-full overflow-hidden">
  <!-- Content Area -->
  <main class="flex-1 overflow-y-auto">
    {#if $activeSettingsTab === 'libraries'}
      <Libraries />
    {:else if $activeSettingsTab === 'scan-settings'}
      <ScanSettings />
    {:else if $activeSettingsTab === 'scanner'}
      <Scanner />
    {:else if $activeSettingsTab === 'users'}
      <Users />
    {:else if $activeSettingsTab === 'advanced'}
      <Advanced />
    {:else if $activeSettingsTab === 'about'}
      <About />
    {/if}
  </main>
</div>
