<script>
  import { activeManagementTab, activeView, hasPermission } from '../store.js';
  import SidebarHeader from '../SidebarHeader.svelte';
  import { 
    LayoutDashboard, 
    Library,
    Image,
    ListMusic, 
    Tags,
    ListChecks,
    Download,
    History, 
    HeartPulse, 
    Users, 
    UserPlus,
    GitBranch, 
    Bell, 
    Info 
  } from '@lucide/svelte';

  const { onnavigate } = $props();

  const tabs = $derived([
    { id: 'overview', label: 'Overzicht', icon: LayoutDashboard },
    { id: 'library', label: 'Bibliotheek', icon: Library },
    { id: 'images', label: 'Afbeeldingen', icon: Image },
    { id: 'playlists', label: 'Afspeellijsten', icon: ListMusic },
    { id: 'tagger', label: 'Tagger', icon: Tags },
    { id: 'genre-curation', label: 'Genre Curatie', icon: ListChecks },
    { id: 'downloaders', label: 'Downloaders', icon: Download },
    { id: 'scrobble', label: 'Scrobble Import', icon: History },
    { id: 'health', label: 'Gezondheid', icon: HeartPulse },
    { id: 'users', label: 'Gebruikers', icon: Users, show: hasPermission('users.read') },
    { id: 'user-requests', label: 'Toegangsverzoeken', icon: UserPlus, show: hasPermission('user-requests.read') },
    { id: 'versions', label: 'Versies', icon: GitBranch },
    { id: 'notifications', label: 'Notificaties', icon: Bell },
    { id: 'about', label: 'Over', icon: Info }
  ].filter(t => t.show !== false));

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
