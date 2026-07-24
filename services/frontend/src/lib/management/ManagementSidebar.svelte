<script>
  import { activeManagementTab, activeView } from '../store.js';
  import SidebarHeader from '../SidebarHeader.svelte';
  import { 
    LayoutDashboard, 
    Library, 
    BarChart3, 
    Image, 
    ListMusic, 
    Tags, 
    Download, 
    History, 
    HeartPulse, 
    Users, 
    GitBranch, 
    Bell, 
    Info 
  } from '@lucide/svelte';

  const { onnavigate } = $props();

  const tabs = [
    { id: 'overview', label: 'Overzicht', icon: LayoutDashboard },
    { id: 'advanced-library', label: 'Advanced Library', icon: Library },
    { id: 'library', label: 'Bibliotheek', icon: Library },
    { id: 'stats', label: 'Statistieken', icon: BarChart3 },
    { id: 'images', label: 'Afbeeldingen', icon: Image },
    { id: 'playlists', label: 'Afspeellijsten', icon: ListMusic },
    { id: 'tagger', label: 'Tagger', icon: Tags },
    { id: 'downloaders', label: 'Downloaders', icon: Download },
    { id: 'scrobble', label: 'Scrobble Import', icon: History },
    { id: 'health', label: 'Gezondheid', icon: HeartPulse },
    { id: 'users', label: 'Gebruikers', icon: Users },
    { id: 'versions', label: 'Versies', icon: GitBranch },
    { id: 'notifications', label: 'Notificaties', icon: Bell },
    { id: 'about', label: 'Over', icon: Info }
  ];

  function goBack() {
    activeView.set('home');
  }

  function setTab(id) {
    activeManagementTab.set(id);
  }
</script>

<nav class="flex flex-col gap-6 h-full bg-black">
  <SidebarHeader onnavigate={onnavigate} />

  <div class="flex flex-col gap-1 overflow-y-auto scrollbar-thin px-3">
    {#each tabs as tab (tab.id)}
      <button
        class="flex items-center gap-4 w-full px-3 py-3 bg-transparent border-none font-bold text-sm cursor-pointer transition-all rounded-md text-left { $activeManagementTab === tab.id ? 'bg-[#282828] text-white' : 'text-[#b3b3b3] hover:text-white hover:bg-[#1a1a1a]' }"
        onclick={() => setTab(tab.id)}
      >
        <tab.icon size={20} />
        {tab.label}
      </button>
    {/each}
  </div>
</nav>
