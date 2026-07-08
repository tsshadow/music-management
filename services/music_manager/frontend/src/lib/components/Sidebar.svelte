<script lang="ts">
  import { Database, Home, Activity, Image, List, Tag, Cloud, Radio, ShieldCheck, Users, LayoutTemplate, Info, ExternalLink } from 'lucide-svelte';

  export let activeTab: string;
  export let onTabChange: (tab: string) => void;
  export let fetchStats: () => void;
  export let fetchPlaylists: () => void;
  export let refreshSystemStatus: () => void;
  export let fetchAbout: () => void;
</script>

<aside class="w-64 bg-black flex flex-col flex-shrink-0">
  <div class="p-6">
    <h1 class="text-white text-xl font-bold flex items-center gap-2">
      <div class="w-8 h-8 bg-spotify-green rounded-full flex items-center justify-center">
        <Database size={18} class="text-black" />
      </div>
      MuMa Control
    </h1>
  </div>
  
  <nav class="flex-1 px-4 space-y-1 overflow-y-auto scrollbar-thin pb-8">
    <div class="pt-4 pb-1 px-4 text-[10px] font-bold text-spotify-lightgray uppercase tracking-widest">Dashboard</div>
    <button 
      on:click={() => onTabChange('home')}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'home' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Home size={20} /> Overview
    </button>
    <button 
      on:click={() => { onTabChange('stats'); fetchStats(); }}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'stats' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Activity size={20} /> Bibliotheek Stats
    </button>

    <div class="pt-4 pb-1 px-4 text-[10px] font-bold text-spotify-lightgray uppercase tracking-widest">Bibliotheek</div>
    <button 
      on:click={() => onTabChange('images')}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'images' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Image size={20} /> Artist Images
    </button>
    <button 
      on:click={() => { onTabChange('playlists'); fetchPlaylists(); }}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'playlists' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <List size={20} /> Dynamic Playlists
    </button>

    <div class="pt-4 pb-1 px-4 text-[10px] font-bold text-spotify-lightgray uppercase tracking-widest">Tools</div>
    <button 
      on:click={() => onTabChange('tagger')}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'tagger' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Tag size={20} /> Tagger
    </button>
    <button 
      on:click={() => onTabChange('downloaders')}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'downloaders' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Cloud size={20} /> Downloaders
    </button>
    <button 
      on:click={() => onTabChange('scrobble')}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'scrobble' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Radio size={20} /> Scrobble Service
    </button>

    <div class="pt-4 pb-1 px-4 text-[10px] font-bold text-spotify-lightgray uppercase tracking-widest">Systeem</div>
    <button 
      on:click={() => { onTabChange('health'); refreshSystemStatus(); }}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'health' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <ShieldCheck size={20} /> Systeem Status
    </button>
    <button 
      on:click={() => onTabChange('users')}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'users' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Users size={20} /> Users
    </button>
    <button 
      on:click={() => onTabChange('versions')}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'versions' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <LayoutTemplate size={20} /> Worker Versions
    </button>
    <button 
      on:click={() => { onTabChange('about'); fetchAbout(); }}
      class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold transition-colors {activeTab === 'about' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      <Info size={20} /> About MuMa
    </button>
    
    <div class="pt-4 mt-4 border-t border-spotify-gray">
      <a 
        href="https://spotify.teunschriks.nl"
        target="_blank"
        class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold text-spotify-lightgray hover:text-white transition-colors"
      >
        <ExternalLink size={20} /> Spotify Sync
      </a>
      <a 
        href="https://scrobbler.teunschriks.nl"
        target="_blank"
        class="w-full flex items-center gap-4 px-4 py-2.5 rounded-md font-bold text-spotify-lightgray hover:text-white transition-colors"
      >
        <ExternalLink size={20} /> Scrobbler UI
      </a>
    </div>
  </nav>
</aside>
