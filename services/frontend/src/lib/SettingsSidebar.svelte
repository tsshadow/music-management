<script>
  import { t } from './i18n/index.js';
  import { activeSettingsTab, activeView } from './store.js';
  import SidebarHeader from './SidebarHeader.svelte';

  // `onselect` lets the mobile drawer close itself once a tab was picked; on
  // the desktop sidebar it is simply not passed.
  const { onnavigate, onselect } = $props();

  // Player settings are personal settings only. Everything that administers the
  // server itself (scanner, libraries, users, API tokens) lives in the
  // management view instead, so admins have one place for admin work.
  const tabs = [
    { id: 'general', labelKey: 'settings.tabs.general', icon: 'M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z' },
    { id: 'advanced', labelKey: 'settings.tabs.advanced', icon: 'M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10zm-6-4h2V7h4V5h-4V3h-2v6z' },
    { id: 'about', labelKey: 'settings.tabs.about', icon: 'M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z' }
  ];

  /**
   * Navigates back to the home view.
   */
  function goBack() {
    activeView.set('home');
  }

  /**
   * Switches the active settings tab.
   *
   * @param {string} id - The tab identifier.
   */
  function setTab(id) {
    activeSettingsTab.set(id);
    if (onselect) onselect(id);
  }
</script>

<nav class="flex flex-col gap-6 h-full bg-black">
  <SidebarHeader onnavigate={onnavigate} />

  <div class="flex flex-col gap-1 px-3">
    {#each tabs as tab (tab.id)}
      <button
        class="flex items-center gap-4 w-full px-3 py-3 bg-transparent border-none font-bold text-sm cursor-pointer transition-all rounded-md text-left { $activeSettingsTab === tab.id ? 'bg-[#282828] text-white' : 'text-[#b3b3b3] hover:text-white hover:bg-[#1a1a1a]' }"
        onclick={() => setTab(tab.id)}
      >
        <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
          <path d={tab.icon}></path>
        </svg>
        {$t(tab.labelKey)}
      </button>
    {/each}
  </div>
</nav>
