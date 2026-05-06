<script>
  import Libraries from './settings/Libraries.svelte';
  import ScanSettings from './settings/ScanSettings.svelte';
  import Scanner from './settings/Scanner.svelte';
  import Users from './settings/Users.svelte';
  import About from './settings/About.svelte';

  export let activeTab = 'libraries';

  const tabs = [
    { id: 'libraries', label: 'Libraries', icon: 'M4 6H2V20C2 21.1 2.9 22 4 22H18V20H4V6ZM20 2H8C6.9 2 6 2.9 6 4V16C6 17.1 6.9 18 8 18H20C21.1 18 22 17.1 22 16V4C22 2.9 21.1 2 20 2ZM20 16H8V4H20V16Z' },
    { id: 'scan-settings', label: 'Scan Settings', icon: 'M19.14 12.94C19.18 12.63 19.2 12.32 19.2 12C19.2 11.68 19.18 11.37 19.14 11.06L21.16 9.48C21.34 9.33 21.39 9.08 21.27 8.89L19.37 5.59C19.25 5.4 19.01 5.32 18.81 5.4L16.43 6.36C15.93 5.98 15.39 5.66 14.81 5.42L14.45 2.89C14.41 2.68 14.22 2.52 14.01 2.52H10.19C9.97 2.52 9.79 2.68 9.75 2.89L9.39 5.42C8.81 5.66 8.27 5.98 7.77 6.36L5.39 5.4C5.19 5.32 4.95 5.4 4.83 5.59L2.93 8.89C2.81 9.08 2.86 9.33 3.04 9.48L5.06 11.06C5.02 11.37 5 11.68 5 12C5 12.32 5.02 12.63 5.06 12.94L3.04 14.52C2.86 14.67 2.81 14.92 2.93 15.11L4.83 18.41C4.95 18.6 5.19 18.68 5.39 18.6L7.77 17.64C8.27 18.02 8.81 18.34 9.39 18.58L9.75 21.11C9.79 21.32 9.97 21.48 10.19 21.48H14.01C14.22 21.48 14.41 21.32 14.45 21.11L14.81 18.58C15.39 18.34 15.93 18.02 16.43 17.64L18.81 18.6C19.01 18.68 19.25 18.6 19.37 18.41L21.27 15.11C21.39 14.92 21.34 14.67 21.16 14.52L19.14 12.94ZM12 15.6C10.01 15.6 8.4 13.99 8.4 12C8.4 10.01 10.01 8.4 12 8.4C13.99 8.4 15.6 10.01 15.6 12C15.6 13.99 13.99 15.6 12 15.6Z' },
    { id: 'scanner', label: 'Scanner', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm4.59-12.42L10 14.17l-2.59-2.58L6 13l4 4 8-8z' },
    { id: 'users', label: 'Users', icon: 'M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z' },
    { id: 'about', label: 'About', icon: 'M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z' }
  ];

  function setTab(id) {
    activeTab = id;
  }
</script>

<div class="flex flex-col h-full bg-[#121212] rounded-lg overflow-hidden">
  <div class="flex flex-1 overflow-hidden">
    <!-- Sidebar -->
    <aside class="w-64 bg-[#000000] p-4 flex flex-col gap-2 border-r border-[#282828]">
      <h2 class="text-xl font-bold mb-4 px-2 text-white">Settings</h2>
      <nav class="flex flex-col gap-1">
        {#each tabs as tab (tab.id)}
          <button 
            class="flex items-center gap-3 px-3 py-2 rounded-md transition-colors text-left border-none cursor-pointer {activeTab === tab.id ? 'bg-[#282828] text-white' : 'text-[#b3b3b3] hover:text-white hover:bg-[#1a1a1a]'}"
            on:click={() => setTab(tab.id)}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d={tab.icon}></path>
            </svg>
            <span class="font-medium">{tab.label}</span>
          </button>
        {/each}
      </nav>
    </aside>

    <!-- Content Area -->
    <main class="flex-1 overflow-y-auto p-8">
      {#if activeTab === 'libraries'}
        <Libraries />
      {:else if activeTab === 'scan-settings'}
        <ScanSettings />
      {:else if activeTab === 'scanner'}
        <Scanner />
      {:else if activeTab === 'users'}
        <Users />
      {:else if activeTab === 'about'}
        <About />
      {/if}
    </main>
  </div>
</div>
