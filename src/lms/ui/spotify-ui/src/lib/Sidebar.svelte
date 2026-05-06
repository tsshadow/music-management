<script>
  import { createEventDispatcher } from 'svelte';
  import { credentials } from './store.js';
  const dispatch = createEventDispatcher();

  export let activeView = 'home';
  let genres = ['Euphoric Hardstyle', 'Hardstyle', 'Mainstream Hardstyle', 'Raw Hardstyle', "Hard Techno", 'Hardcore', 'Mainstream Hardcore', "Frenchcore", 'Industrial Hardcore', 'Uptempo Hardcore', 'Terror', 'Zaagtempo']

  const menuItems = [
    { id: 'home', label: 'Home', icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    { id: 'radar', label: 'Release Radar', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm4.59-12.42L10 14.17l-2.59-2.58L6 13l4 4 8-8-1.41-1.42z' },
    { id: 'songs', label: 'Songs', icon: 'M15.5 2.157a.5.5 0 0 0-.707 0l-12 12A.5.5 0 0 0 3 15h3v5.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V15h3a.5.5 0 0 0 .207-.843l-12-12z' },
    { id: 'sets', label: 'Sets', icon: 'M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm1-13h-2v6h6v-2h-4z' },
  ];

  function navigate(id) {
    dispatch('navigate', id);
  }

  function logout() {
    credentials.set({ url: window.location.origin, username: '', password: '' });
  }
</script>

<nav class="p-6 flex flex-col gap-6 h-full">
  <div class="flex items-center gap-2 px-3 text-xl font-bold">
    <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
        <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.491 17.306c-.215.353-.675.465-1.028.25-2.864-1.75-6.467-2.146-10.713-1.176-.403.092-.806-.16-.898-.563-.092-.403.16-.806.563-.898 4.647-1.064 8.623-.615 11.826 1.34.353.215.465.675.25 1.028zm1.464-3.264c-.272.441-.848.583-1.289.311-3.279-2.015-8.279-2.599-12.158-1.421-.497.151-1.025-.13-1.176-.627-.151-.497.13-1.025.627-1.176 4.433-1.345 9.947-.693 13.7 1.613.441.272.583.848.311 1.289zm.126-3.407C15.222 8.356 8.85 8.144 5.122 9.276c-.595.181-1.229-.153-1.409-.748s.153-1.229.748-1.409c4.275-1.299 11.319-1.054 15.767 1.587.535.318.708 1.009.39 1.544-.318.535-1.009.708-1.544.39z"/>
    </svg>
    <span>LMS Spotify</span>
  </div>

  <ul class="list-none p-0 m-0">
    {#each menuItems as item}
      <li class="mb-1 {activeView === item.id ? 'text-white' : 'text-[#b3b3b3]'}">
        <button 
          class="flex items-center gap-4 w-full px-3 py-2 bg-transparent border-none font-bold text-sm cursor-pointer transition-colors hover:text-white text-left"
          on:click={() => navigate(item.id)}
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
      <li><button class="w-full px-3 py-2 bg-transparent border-none text-[#b3b3b3] text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" on:click={() => navigate('playlists')}>Afspeellijsten</button></li>
      <li><button class="w-full px-3 py-2 bg-transparent border-none text-[#b3b3b3] text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" on:click={() => navigate('artists')}>Artiesten</button></li>
      <li><button class="w-full px-3 py-2 bg-transparent border-none text-[#b3b3b3] text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" on:click={() => navigate('albums')}>Albums</button></li>
    </ul>
  </div>

  <div class="genres overflow-y-auto scrollbar-hide">
    <h3 class="px-3 text-[12px] text-[#b3b3b3] tracking-[1.5px] mb-3">GENRES</h3>
    <ul class="list-none p-0 m-0">
      {#each genres as genre}
        <li>
          <button class="w-full px-3 py-2 bg-transparent border-none text-[#b3b3b3] text-sm font-medium cursor-pointer transition-colors hover:text-white text-left" on:click={() => navigate(`genre:${genre}`)}>{genre}</button>
        </li>
      {/each}
    </ul>
  </div>

  <div class="h-px bg-[#282828] mx-3"></div>

  <div class="px-3 mt-auto flex flex-col gap-1">
    <button class="flex items-center gap-3 text-[#b3b3b3] no-underline text-sm font-semibold py-2.5 transition-colors hover:text-white bg-transparent border-none cursor-pointer w-full text-left" on:click={logout}>
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
        <path d="M10.09 15.59L11.5 17l5-5-5-5-1.41 1.41L12.67 11H3v2h9.67l-2.58 2.59zM19 3H5c-1.11 0-2 .9-2 2v4h2V5h14v14H5v-4H3v4c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z"/>
      </svg>
      Uitloggen
    </button>
    <a href="/legacy" class="flex items-center gap-3 text-[#b3b3b3] no-underline text-sm font-semibold py-2.5 transition-colors hover:text-white bg-transparent border-none cursor-pointer w-full text-left">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
        <path d="M13 3L16.29 6.29L13.6 8.99L15.01 10.4L17.71 7.71L21 11V3H13M3 21H11V13H3V21M5 15H9V19H5V15M3 11H11V3H3V11M5 5H9V9H5V5M13 21H21V13H13V21M15 15H19V19H15V15Z"/>
      </svg>
      Oude UI (Legacy)
    </a>
  </div>
</nav>

<style>
</style>
