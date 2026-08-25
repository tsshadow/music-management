<script>
  import { t } from '../i18n/index.js';
  import { activeManagementTab, hasPermission } from '../store.js';
  import { MANAGEMENT_GROUPS } from '../router.js';
  import SidebarHeader from '../SidebarHeader.svelte';
  import {
    ChevronRight,
    LayoutDashboard,
    Library,
    Image,
    ListMusic,
    Tags,
    ListChecks,
    Podcast,
    Newspaper,
    Radio,
    Download,
    History,
    HeartPulse,
    ScanLine,
    FolderTree,
    Users,
    UserPlus,
    ScrollText,
    SlidersHorizontal
  } from '@lucide/svelte';

  // `onselect` lets the mobile drawer close itself once a tab was picked; on
  // the desktop sidebar it is simply not passed.
  const { onnavigate, onselect } = $props();

  /**
   * What each page shows in the sidebar, and what it takes to see it.
   *
   * The order lives in `MANAGEMENT_GROUPS`; this is only the per-page presentation,
   * keyed by tab id so the two cannot drift out of order with each other.
   */
  const PAGES = {
    'overview': { labelKey: 'management.tabs.overview', icon: LayoutDashboard },
    'library': { labelKey: 'management.tabs.library', icon: Library },
    'scanner': { labelKey: 'management.tabs.scanner', icon: ScanLine },
    'images': { labelKey: 'management.tabs.images', icon: Image },
    'playlists': { labelKey: 'management.tabs.playlists', icon: ListMusic },
    'tagger': { labelKey: 'management.tabs.tagger', icon: Tags },
    'genre-curation': { labelKey: 'management.tabs.genreCuration', icon: ListChecks },
    'label-proposals': { labelKey: 'management.tabs.labelProposals', icon: Tags },
    'podcast-curation': { labelKey: 'management.tabs.podcastCuration', icon: Podcast },
    'downloaders': { labelKey: 'management.tabs.downloaders', icon: Download },
    'radio': { labelKey: 'management.tabs.radio', icon: Radio, permission: 'radio.manage' },
    'news': { labelKey: 'management.tabs.news', icon: Newspaper, permission: 'news.manage' },
    'users': { labelKey: 'management.tabs.users', icon: Users, permission: 'users.read' },
    'user-requests': { labelKey: 'management.tabs.userRequests', icon: UserPlus, permission: 'user-requests.read' },
    'health': { labelKey: 'management.tabs.health', icon: HeartPulse },
    'events': { labelKey: 'management.tabs.events', icon: ScrollText },
    'scrobble': { labelKey: 'management.tabs.scrobble', icon: History },
    'libraries': { labelKey: 'management.tabs.libraries', icon: FolderTree },
    'config': { labelKey: 'management.tabs.config', icon: SlidersHorizontal, permission: 'config.manage' }
  };

  const OPEN_KEY = 'muma_management_groups_open';

  /**
   * Which groups were left open the last time this browser was used.
   *
   * @returns {string[]}
   */
  function storedOpen() {
    try {
      const raw = localStorage.getItem(OPEN_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      // A browser that refuses storage still gets a working sidebar, just a forgetful one.
      return [];
    }
  }

  let open = $state(storedOpen());

  /**
   * The groups as rendered: pages the viewer may not see are dropped, and a group
   * that empties out entirely disappears rather than opening onto nothing.
   */
  const groups = $derived(
    MANAGEMENT_GROUPS.map((group) => ({
      ...group,
      items: group.pages
        .filter((id) => !PAGES[id].permission || hasPermission(PAGES[id].permission))
        .map((id) => ({ id, ...PAGES[id] }))
    })).filter((group) => group.items.length > 0)
  );

  /**
   * A group is expanded when the viewer opened it, or when it owns the active tab --
   * otherwise a deep link into /management/scanner would land inside a folded group.
   *
   * @param {Object} group - A group as rendered, with its permitted items.
   * @returns {boolean} Whether its pages are shown.
   */
  function isExpanded(group) {
    return open.includes(group.id) || group.items.some((item) => item.id === $activeManagementTab);
  }

  /**
   * Folds a group open or shut, and remembers the choice for the next visit.
   *
   * @param {string} id - The group id.
   */
  function toggle(id) {
    open = open.includes(id) ? open.filter((entry) => entry !== id) : [...open, id];
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify(open));
    } catch {
      // See storedOpen: storage is a convenience, not a requirement.
    }
  }

  function setTab(id) {
    activeManagementTab.set(id);
    if (onselect) onselect(id);
  }
</script>

<nav class="flex flex-col gap-6 h-full bg-black">
  <SidebarHeader onnavigate={onnavigate} />

  <div class="flex flex-col gap-1 overflow-y-auto scrollbar-thin px-3">
    {#each groups as group (group.id)}
      {#if group.labelKey === null}
        {@const item = group.items[0]}
        <button
          class="flex items-center gap-4 w-full px-3 py-3 bg-transparent border-none font-bold text-sm cursor-pointer transition-all rounded-md text-left { $activeManagementTab === item.id ? 'bg-[#282828] text-white' : 'text-[#b3b3b3] hover:text-white hover:bg-[#1a1a1a]' }"
          onclick={() => setTab(item.id)}
        >
          <item.icon size={20} />
          {$t(item.labelKey)}
        </button>
      {:else}
        <button
          class="flex items-center gap-3 w-full px-3 py-3 bg-transparent border-none font-bold text-sm cursor-pointer transition-all rounded-md text-left text-[#b3b3b3] hover:text-white hover:bg-[#1a1a1a]"
          onclick={() => toggle(group.id)}
          aria-expanded={isExpanded(group)}
        >
          <ChevronRight size={16} class="transition-transform {isExpanded(group) ? 'rotate-90' : ''}" />
          {$t(group.labelKey)}
        </button>
        {#if isExpanded(group)}
          {#each group.items as item (item.id)}
            <button
              class="flex items-center gap-4 w-full pl-8 pr-3 py-2.5 bg-transparent border-none font-bold text-sm cursor-pointer transition-all rounded-md text-left { $activeManagementTab === item.id ? 'bg-[#282828] text-white' : 'text-[#b3b3b3] hover:text-white hover:bg-[#1a1a1a]' }"
              onclick={() => setTab(item.id)}
            >
              <item.icon size={18} />
              {$t(item.labelKey)}
            </button>
          {/each}
        {/if}
      {/if}
    {/each}
  </div>
</nav>
