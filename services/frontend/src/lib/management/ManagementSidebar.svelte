<script>
  import { t } from '../i18n/index.js';
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
    ScanLine,
    FolderTree,
    Users,
    UserPlus,
    GitBranch, 
    Bell, 
    Info 
  } from '@lucide/svelte';

  const { onnavigate } = $props();

  const tabs = $derived([
    { id: 'overview', labelKey: 'management.tabs.overview', icon: LayoutDashboard },
    { id: 'library', labelKey: 'management.tabs.library', icon: Library },
    { id: 'libraries', labelKey: 'management.tabs.libraries', icon: FolderTree },
    { id: 'scanner', labelKey: 'management.tabs.scanner', icon: ScanLine },
    { id: 'images', labelKey: 'management.tabs.images', icon: Image },
    { id: 'playlists', labelKey: 'management.tabs.playlists', icon: ListMusic },
    { id: 'tagger', labelKey: 'management.tabs.tagger', icon: Tags },
    { id: 'genre-curation', labelKey: 'management.tabs.genreCuration', icon: ListChecks },
    { id: 'downloaders', labelKey: 'management.tabs.downloaders', icon: Download },
    { id: 'scrobble', labelKey: 'management.tabs.scrobble', icon: History },
    { id: 'health', labelKey: 'management.tabs.health', icon: HeartPulse },
    { id: 'users', labelKey: 'management.tabs.users', icon: Users, show: hasPermission('users.read') },
    { id: 'user-requests', labelKey: 'management.tabs.userRequests', icon: UserPlus, show: hasPermission('user-requests.read') },
    { id: 'versions', labelKey: 'management.tabs.versions', icon: GitBranch },
    { id: 'notifications', labelKey: 'management.tabs.notifications', icon: Bell },
    { id: 'about', labelKey: 'management.tabs.about', icon: Info }
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
        {$t(tab.labelKey)}
      </button>
    {/each}
  </div>
</nav>
