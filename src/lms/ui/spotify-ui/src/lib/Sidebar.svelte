<script>
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  export let activeView = 'home';

  const menuItems = [
    { id: 'home', label: 'Home', icon: 'M12.5 3.5a.5.5 0 0 1 .5 0l9 5.25a.5.5 0 0 1 .25.433V20.5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5v-5a.5.5 0 0 0-.5-.5h-2a.5.5 0 0 0-.5.5v5a.5.5 0 0 1-.5.5h-5a.5.5 0 0 1-.5-.5V9.183a.5.5 0 0 1 .25-.433z' },
    { id: 'radar', label: 'Release Radar', icon: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm4.59-12.42L10 14.17l-2.59-2.58L6 13l4 4 8-8-1.41-1.42z' },
    { id: 'songs', label: 'Songs', icon: 'M15.5 2.157a.5.5 0 0 0-.707 0l-12 12A.5.5 0 0 0 3 15h3v5.5a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5V15h3a.5.5 0 0 0 .207-.843l-12-12z' },
    { id: 'sets', label: 'Sets', icon: 'M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm1-13h-2v6h6v-2h-4z' },
  ];

  function navigate(id) {
    dispatch('navigate', id);
  }
</script>

<nav class="sidebar">
  <div class="logo">
    <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
        <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.491 17.306c-.215.353-.675.465-1.028.25-2.864-1.75-6.467-2.146-10.713-1.176-.403.092-.806-.16-.898-.563-.092-.403.16-.806.563-.898 4.647-1.064 8.623-.615 11.826 1.34.353.215.465.675.25 1.028zm1.464-3.264c-.272.441-.848.583-1.289.311-3.279-2.015-8.279-2.599-12.158-1.421-.497.151-1.025-.13-1.176-.627-.151-.497.13-1.025.627-1.176 4.433-1.345 9.947-.693 13.7 1.613.441.272.583.848.311 1.289zm.126-3.407C15.222 8.356 8.85 8.144 5.122 9.276c-.595.181-1.229-.153-1.409-.748s.153-1.229.748-1.409c4.275-1.299 11.319-1.054 15.767 1.587.535.318.708 1.009.39 1.544-.318.535-1.009.708-1.544.39z"/>
    </svg>
    <span>LMS Spotify</span>
  </div>

  <ul class="nav-list">
    {#each menuItems as item}
      <li class:active={activeView === item.id}>
        <button on:click={() => navigate(item.id)}>
          <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
            <path d={item.icon}></path>
          </svg>
          {item.label}
        </button>
      </li>
    {/each}
  </ul>

  <div class="divider"></div>

  <div class="library">
    <h3>JOUW BIBLIOTHEEK</h3>
    <ul>
      <li><button on:click={() => navigate('playlists')}>Afspeellijsten</button></li>
      <li><button on:click={() => navigate('artists')}>Artiesten</button></li>
      <li><button on:click={() => navigate('albums')}>Albums</button></li>
    </ul>
  </div>

  <div class="genres">
    <h3>GENRES</h3>
    <ul>
      <li><button on:click={() => navigate('genre:Hardcore')}>Hardcore</button></li>
      <li><button on:click={() => navigate('genre:Raw Hardstyle')}>Raw Hardstyle</button></li>
      <li><button on:click={() => navigate('genre:Frenchcore')}>Frenchcore</button></li>
      <li><button on:click={() => navigate('genre:Uptempo')}>Uptempo</button></li>
    </ul>
  </div>
</nav>

<style>
  .sidebar {
    padding: 24px 12px;
    display: flex;
    flex-direction: column;
    gap: 24px;
    height: 100%;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 12px;
    font-size: 20px;
    font-weight: 700;
  }

  .nav-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .nav-list li {
    margin-bottom: 4px;
  }

  .nav-list li button {
    display: flex;
    align-items: center;
    gap: 16px;
    width: 100%;
    padding: 8px 12px;
    background: none;
    border: none;
    color: #b3b3b3;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    transition: color 0.2s;
    text-align: left;
  }

  .nav-list li.active button {
    color: #fff;
  }

  .nav-list li button:hover {
    color: #fff;
  }

  .divider {
    height: 1px;
    background-color: #282828;
    margin: 0 12px;
  }

  .library h3, .genres h3 {
    padding: 0 12px;
    font-size: 12px;
    color: #b3b3b3;
    letter-spacing: 1.5px;
    margin-bottom: 12px;
  }

  .library ul, .genres ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .library li button, .genres li button {
    width: 100%;
    padding: 8px 12px;
    background: none;
    border: none;
    color: #b3b3b3;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: color 0.2s;
    text-align: left;
  }

  .library li button:hover {
    color: #fff;
  }
</style>
