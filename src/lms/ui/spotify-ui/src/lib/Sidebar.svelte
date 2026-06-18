<script>
  import { viewMode } from './store.js';
  const { activeView = 'home', onnavigate } = $props();
  const genres = ['Euphoric Hardstyle', 'Hardstyle', 'Mainstream Hardstyle', 'Raw Hardstyle', "Hard Techno", 'Hardcore', 'Mainstream Hardcore', "Frenchcore", 'Industrial Hardcore', 'Uptempo Hardcore', 'Terror', 'Zaagtempo']

  const menuItems = $derived([
    { id: 'home', label: 'Home', icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    { id: 'radar', label: 'Release Radar', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm4.59-12.42L10 14.17l-2.59-2.58L6 13l4 4 8-8-1.41-1.42z' },
    { 
      id: $viewMode === 'sets' ? 'sets' : 'songs', 
      label: $viewMode === 'sets' ? 'Sets' : 'Songs', 
      icon: $viewMode === 'sets' 
        ? 'M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm1-13h-2v6h6v-2h-4z' 
        : 'M15.5 2.157a.5.5 0 0 0-.707 0l-12 12A.5.5 0 0 0 3 15h3v5.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V15h3a.5.5 0 0 0 .207-.843l-12-12z' 
    },
  ]);

  /**
   * Triggers navigation to a specific view.
   * 
   * @param {string} id - The view identifier.
   */
  function navigate(id) {
    if (onnavigate) onnavigate(id);
  }
</script>

<nav class="p-6 flex flex-col gap-6 h-full">
  <div class="flex items-center gap-2 px-3 text-xl font-bold">
    <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
        <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.491 17.306c-.215.353-.675.465-1.028.25-2.864-1.75-6.467-2.146-10.713-1.176-.403.092-.806-.16-.898-.563-.092-.403.16-.806.563-.898 4.647-1.064 8.623-.615 11.826 1.34.353.215.465.675.25 1.028zm1.464-3.264c-.272.441-.848.583-1.289.311-3.279-2.015-8.279-2.599-12.158-1.421-.497.151-1.025-.13-1.176-.627-.151-.497.13-1.025.627-1.176 4.433-1.345 9.947-.693 13.7 1.613.441.272.583.848.311 1.289zm.126-3.407C15.222 8.356 8.85 8.144 5.122 9.276c-.595.181-1.229-.153-1.409-.748s.153-1.229.748-1.409c4.275-1.299 11.319-1.054 15.767 1.587.535.318.708 1.009.39 1.544-.318.535-1.009.708-1.544.39z"/>
    </svg>
    <span>LMS Spotify</span>
  </div>

  <div class="px-3 py-4">
    <div class="flex items-center gap-3">
      <button class="bg-transparent border-none p-0 text-[13px] font-bold {$viewMode === 'songs' ? 'text-white' : 'text-[#b3b3b3]'} transition-colors cursor-pointer" onclick={() => viewMode.set('songs')}>Songs</button>
      <button 
        class="relative flex-shrink-0 w-10 h-5 rounded-full bg-[#282828] transition-colors duration-200 hover:bg-[#3e3e3e]"
        onclick={() => viewMode.update(m => m === 'songs' ? 'sets' : 'songs')}
        aria-label="Toggle mode"
      >
        <div 
          class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full transition-transform duration-200 {$viewMode === 'sets' ? 'translate-x-5 bg-brand-blue' : 'bg-brand-green'}"
        ></div>
      </button>
      <button class="bg-transparent border-none p-0 text-[13px] font-bold {$viewMode === 'sets' ? 'text-white' : 'text-[#b3b3b3]'} transition-colors cursor-pointer" onclick={() => viewMode.set('sets')}>Sets</button>
    </div>
  </div>

  <ul class="list-none p-0 m-0">
    {#each menuItems as item (item.id)}
      <li class="mb-1 {activeView === item.id ? 'text-white' : 'text-[#b3b3b3]'}">
        <button 
          class="flex items-center gap-4 w-full px-3 py-2 bg-transparent border-none font-bold text-sm cursor-pointer transition-colors hover:text-white text-left"
          onclick={() => navigate(item.id)}
        >
          <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
            <path d={item.icon}></path>
          </svg>
          {item.label}
        </button>
      </li>
    {/each}
  </ul>

  <div class="h-px bg-[#282828] mx-3"></div>

  <div class="library">
    <h3 class="px-3 text-[12px] text-[#b3b3b3] tracking-[1.5px] mb-3">JOUW BIBLIOTHEEK</h3>
    <ul class="list-none p-0 m-0">
      <li><button class="w-full px-3 py-2 bg-transparent border-none {activeView === 'playlists' ? 'text-white' : 'text-[#b3b3b3]'} text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" onclick={() => navigate('playlists')}>Afspeellijsten</button></li>
      <li><button class="w-full px-3 py-2 bg-transparent border-none {activeView === 'artists' ? 'text-white' : 'text-[#b3b3b3]'} text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" onclick={() => navigate('artists')}>Artiesten</button></li>
      <li><button class="w-full px-3 py-2 bg-transparent border-none {activeView === 'albums' ? 'text-white' : 'text-[#b3b3b3]'} text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" onclick={() => navigate('albums')}>Albums</button></li>
      <li><button class="w-full px-3 py-2 bg-transparent border-none {activeView === 'genres' ? 'text-white' : 'text-[#b3b3b3]'} text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" onclick={() => navigate('genres')}>Genres</button></li>
    </ul>
  </div>

  <div class="genres overflow-y-auto scrollbar-hide">
    <h3 class="px-3 text-[12px] text-[#b3b3b3] tracking-[1.5px] mb-3">GENRES</h3>
    <ul class="list-none p-0 m-0">
      {#each genres as genre (genre)}
        <li>
          <button class="w-full px-3 py-2 bg-transparent border-none {activeView === `genre:${genre}` ? 'text-white' : 'text-[#b3b3b3]'} text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" onclick={() => navigate(`genre:${genre}`)}>{genre}</button>
        </li>
      {/each}
    </ul>
  </div>
</nav>

<style>
</style>
