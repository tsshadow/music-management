<script>
  import { onMount } from 'svelte';
  import { 
    Search, 
    Filter, 
    List, 
    Info, 
    PieChart, 
    ChevronRight, 
    Star, 
    Clock, 
    Music, 
    Calendar,
    Tag,
    Activity,
    Mic2,
    Volume2,
    Disc,
    User,
    Hash,
    RefreshCw
  } from '@lucide/svelte';

  export let API_BASE;
  export let getHeaders;
  export const onMessage = undefined;
  export let onError;

  // State
  let tracks = [];
  let availableGenres = [];
  let stats = {
    total_songs: 0,
    total_artists: 0,
    total_albums: 0,
    total_genres: 0,
    avg_bpm: 0,
    avg_rating: 4.3,
    total_duration_hours: 0
  };
  let loading = true;
  let selectedTrack = null;
  let searchQuery = "";
  let activeTab = 'library'; // 'library' or 'analytics'
  let filters = {
    genres: [],
    keys: [],
    moods: [],
    bpmRange: [0, 250],
    rating: 0
  };

  // UI State
  let showInspector = true;
  let showFilters = true;

  async function fetchGenres() {
    try {
      const res = await fetch(`${API_BASE}/api/library/genres`, {
        headers: getHeaders()
      });
      if (res.ok) {
        availableGenres = await res.json();
      }
    } catch (err) {
      console.error("Failed to fetch genres", err);
    }
  }

  async function fetchAdvancedLibrary() {
    loading = true;
    try {
      const genreParams = filters.genres.length > 0 ? `&genres=${filters.genres.join(',')}` : '';
      const bpmParams = `&bpm_min=${filters.bpmRange[0]}&bpm_max=${filters.bpmRange[1]}`;
      
      const res = await fetch(`${API_BASE}/api/library/advanced?q=${searchQuery}${genreParams}${bpmParams}&limit=100`, {
        headers: getHeaders()
      });
      
      if (res.ok) {
        const data = await res.json();
        tracks = data.tracks;
        
        // Enhance tracks with real and fallback data
        tracks = tracks.map(t => ({
          ...t,
          energy: t.energy || 0,
          danceability: t.danceability || 0,
          valence: t.valence || 0,
          popularity: t.popularity || 0,
          key: t.musical_key || t.key || '?',
          lyrics: "Lyrics not available for this track."
        }));

        if (data.stats) {
          stats.avg_bpm = Math.round(data.stats.avg_bpm || 0);
          stats.total_songs = data.total;
          stats.total_artists = data.stats.artist_count || 0;
        }
      }
      
      // Fetch global stats if not already fetched
      if (stats.total_genres === 0) {
        const statsRes = await fetch(`${API_BASE}/api/stats`, {
          headers: getHeaders()
        });
        if (statsRes.ok) {
          const statsData = await statsRes.json();
          stats.total_genres = statsData.top_genres?.length || 0;
          stats.total_duration_hours = Math.round(statsData.total_tracks * 3.5 / 60);
          stats.total_albums = statsData.total_albums || 0;
        }
      }
    } catch (err) {
      onError("Failed to load advanced library.");
    } finally {
      loading = false;
    }
  }

  function handleSearch(e) {
    if (e.key === 'Enter') {
      fetchAdvancedLibrary();
    }
  }

  function toggleGenre(genre) {
    if (filters.genres.includes(genre)) {
      filters.genres = filters.genres.filter(g => g !== genre);
    } else {
      filters.genres = [...filters.genres, genre];
    }
    fetchAdvancedLibrary();
  }

  onMount(() => {
    fetchGenres();
    fetchAdvancedLibrary();
  });

  function selectTrack(track) {
    selectedTrack = track;
  }

  function toggleInspector() {
    showInspector = !showInspector;
  }

  function toggleFilters() {
    showFilters = !showFilters;
  }
</script>

<div class="flex flex-col h-full overflow-hidden -m-8">
  <!-- Header / Quick Stats -->
  <div class="bg-black/40 border-b border-white/10 p-4 flex justify-between items-center shrink-0">
    <div class="flex gap-8 overflow-x-auto no-scrollbar py-2">
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold">Songs</span>
        <span class="text-xl font-black text-white">{stats.total_songs.toLocaleString()}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold">Artists</span>
        <span class="text-xl font-black text-white">{stats.total_artists.toLocaleString()}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold">Genres</span>
        <span class="text-xl font-black text-white">{stats.total_genres}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold">Avg BPM</span>
        <span class="text-xl font-black text-white">{stats.avg_bpm}</span>
      </div>
      <div class="flex flex-col">
        <span class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold">Duration</span>
        <span class="text-xl font-black text-white">{stats.total_duration_hours}h</span>
      </div>
    </div>

    <div class="flex gap-2">
      <button 
        class="p-2 rounded-md transition-colors {activeTab === 'library' ? 'bg-brand text-black' : 'hover:bg-white/5 text-white'}"
        on:click={() => activeTab = 'library'}
        title="Library View"
      >
        <List size={20} />
      </button>
      <button 
        class="p-2 rounded-md transition-colors {activeTab === 'analytics' ? 'bg-brand text-black' : 'hover:bg-white/5 text-white'}"
        on:click={() => activeTab = 'analytics'}
        title="Analytics View"
      >
        <PieChart size={20} />
      </button>
    </div>
  </div>

  <!-- Global Search Bar -->
  <div class="bg-[#121212] border-b border-white/5 p-4 flex gap-4 items-center shrink-0">
    <div class="relative flex-1">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 text-[#b3b3b3]" size={18} />
      <input 
        type="text" 
        bind:value={searchQuery}
        on:keydown={handleSearch}
        placeholder="Search title, artist, album, tags, bpm, key... (Press Enter)"
        class="w-full bg-[#242424] border-none rounded-full py-2.5 pl-10 pr-4 text-sm focus:ring-2 focus:ring-brand transition-all outline-none"
      />
    </div>
    <button 
      on:click={toggleFilters}
      class="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 hover:bg-white/5 transition-all text-sm font-bold {showFilters ? 'text-brand border-brand/50' : 'text-white'}"
    >
      <Filter size={16} />
      Filters
    </button>
    <button 
      on:click={toggleInspector}
      class="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 hover:bg-white/5 transition-all text-sm font-bold {showInspector ? 'text-brand border-brand/50' : 'text-white'}"
    >
      <Info size={16} />
      Inspector
    </button>
  </div>

  <!-- Main Content Area -->
  <div class="flex flex-1 min-h-0 overflow-hidden">
    
    <!-- Left Column: Filters -->
    {#if showFilters}
      <div class="w-64 border-r border-white/5 bg-[#121212] overflow-y-auto p-6 flex flex-col gap-8 shrink-0">
        <div>
          <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-4">Genres</h3>
          <div class="flex flex-col gap-1 max-h-60 overflow-y-auto pr-2 scrollbar-thin">
            {#each availableGenres as genre (genre)}
              <label class="flex items-center gap-3 cursor-pointer group py-1">
                <input 
                  type="checkbox" 
                  class="accent-brand rounded" 
                  checked={filters.genres.includes(genre)}
                  on:change={() => toggleGenre(genre)}
                />
                <span class="text-xs text-[#b3b3b3] group-hover:text-white transition-colors truncate">{genre}</span>
              </label>
            {/each}
          </div>
        </div>

        <div>
          <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-4">Metadata</h3>
          <div class="flex flex-col gap-2">
            <label class="flex items-center gap-3 cursor-pointer group">
              <input type="checkbox" class="accent-brand rounded" />
              <span class="text-sm text-[#b3b3b3] group-hover:text-white transition-colors">Favorites Only</span>
            </label>
            <label class="flex items-center gap-3 cursor-pointer group">
              <input type="checkbox" class="accent-brand rounded" />
              <span class="text-sm text-[#b3b3b3] group-hover:text-white transition-colors">Recently Added</span>
            </label>
            <label class="flex items-center gap-3 cursor-pointer group">
              <input type="checkbox" class="accent-brand rounded" />
              <span class="text-sm text-[#b3b3b3] group-hover:text-white transition-colors">Needs Review</span>
            </label>
          </div>
        </div>

        <div>
          <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-4">Key / Camelot</h3>
          <div class="grid grid-cols-4 gap-1">
            {#each ['C', 'Cm', 'C#', 'C#m', 'D', 'Dm', 'D#', 'D#m', 'E', 'Em', 'F', 'Fm'] as key (key)}
              <button class="text-[10px] p-1 border border-white/10 rounded hover:border-brand/50 hover:bg-brand/10 transition-all">
                {key}
              </button>
            {/each}
          </div>
        </div>

        <div>
          <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-4">Mood</h3>
          <div class="flex flex-wrap gap-2">
            {#each ['Happy', 'Sad', 'Dark', 'Epic', 'Chill', 'Energetic'] as mood (mood)}
              <button class="px-3 py-1 bg-[#242424] text-[11px] rounded-full border border-white/5 hover:border-brand/50 transition-all">
                {mood}
              </button>
            {/each}
          </div>
        </div>

        <div>
          <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-4">Vocals</h3>
          <div class="flex flex-col gap-2">
            {#each ['Male', 'Female', 'Instrumental', 'Choir', 'Rap'] as vocal (vocal)}
              <label class="flex items-center gap-3 cursor-pointer group">
                <input type="checkbox" class="accent-brand rounded" />
                <span class="text-sm text-[#b3b3b3] group-hover:text-white transition-colors">{vocal}</span>
              </label>
            {/each}
          </div>
        </div>
      </div>
    {/if}

    <!-- Central Column: Table or Analytics -->
    <div class="flex-1 min-w-0 overflow-y-auto bg-black/20 flex flex-col">
      {#if activeTab === 'library'}
        <table class="w-full text-left text-sm border-collapse">
          <thead class="sticky top-0 bg-[#121212] z-10 border-b border-white/10 shadow-xl">
            <tr class="text-[#b3b3b3] uppercase text-[10px] tracking-widest font-black">
              <th class="px-4 py-4 w-8"><Star size={14} /></th>
              <th class="px-4 py-4">Title</th>
              <th class="px-4 py-4">Artist</th>
              <th class="px-4 py-4">Label</th>
              <th class="px-4 py-4">BPM</th>
              <th class="px-4 py-4">Key</th>
              <th class="px-4 py-4">Genre</th>
              <th class="px-4 py-4 text-right"><Clock size={14} class="inline" /></th>
            </tr>
          </thead>
          <tbody>
            {#if loading}
              <tr>
                <td colspan="8" class="px-4 py-20 text-center text-[#b3b3b3]">
                  <div class="flex flex-col items-center gap-4">
                    <RefreshCw class="animate-spin text-brand" size={32} />
                    <span>Analyzing Library...</span>
                  </div>
                </td>
              </tr>
            {:else if tracks.length === 0}
              <tr>
                <td colspan="8" class="px-4 py-20 text-center text-[#b3b3b3]">No tracks found matching your filters.</td>
              </tr>
            {:else}
              {#each tracks as track (track.id)}
                <tr 
                  class="border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer group {selectedTrack?.id === track.id ? 'bg-white/10' : ''}"
                  on:click={() => selectTrack(track)}
                >
                  <td class="px-4 py-3">
                    <Star size={14} class="{track.rating > 4 ? 'fill-brand text-brand' : 'text-[#535353]'}" />
                  </td>
                  <td class="px-4 py-3">
                    <div class="flex items-center gap-3">
                      <div class="w-10 h-10 bg-[#282828] rounded flex items-center justify-center shrink-0 overflow-hidden shadow-lg">
                        {#if track.cover}
                          <img src={track.cover} alt="" class="w-full h-full object-cover" />
                        {:else}
                          <Disc size={20} class="text-[#535353]" />
                        {/if}
                      </div>
                      <div class="flex flex-col min-w-0">
                        <span class="font-bold text-white truncate group-hover:text-brand transition-colors">{track.title}</span>
                        {#if track.ml_genre}
                          <span class="text-[9px] bg-brand/10 text-brand px-1 py-0.5 rounded self-start font-bold uppercase tracking-tighter border border-brand/20">ML: {track.ml_genre}</span>
                        {/if}
                      </div>
                    </div>
                  </td>
                  <td class="px-4 py-3 text-[#b3b3b3] truncate">{track.artist || '-'}</td>
                  <td class="px-4 py-3 text-[#b3b3b3] truncate font-mono text-[11px]">{track.label || '-'}</td>
                  <td class="px-4 py-3 text-[#b3b3b3] font-mono">{track.bpm ? Math.round(track.bpm) : '-'}</td>
                  <td class="px-4 py-3">
                    <span class="px-2 py-1 bg-blue-500/10 text-blue-400 rounded text-xs font-bold border border-blue-500/20">{track.key}</span>
                  </td>
                  <td class="px-4 py-3">
                    <span class="text-[11px] text-[#b3b3b3]">{track.genre || '-'}</span>
                  </td>
                  <td class="px-4 py-3 text-right text-[#b3b3b3] font-mono">
                    {track.duration_secs ? `${Math.floor(track.duration_secs / 60)}:${(Math.floor(track.duration_secs % 60)).toString().padStart(2, '0')}` : '-'}
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      {:else if activeTab === 'analytics'}
        <div class="p-8 grid grid-cols-1 md:grid-cols-2 gap-8">
          <div class="bg-black/40 p-6 rounded-xl border border-white/5 shadow-2xl">
            <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-6 flex items-center gap-2">
              <PieChart size={16} class="text-brand" />
              Genre Distribution
            </h3>
            <div class="flex flex-col gap-4">
              {#each [['House', 42], ['Techno', 28], ['Trance', 15], ['DnB', 10], ['Ambient', 5]] as [genre, pct] (genre)}
                <div class="flex flex-col gap-1">
                  <div class="flex justify-between text-xs mb-1">
                    <span class="text-white font-bold">{genre}</span>
                    <span class="text-[#b3b3b3]">{pct}%</span>
                  </div>
                  <div class="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                    <div class="h-full bg-brand rounded-full" style="width: {pct}%"></div>
                  </div>
                </div>
              {/each}
            </div>
          </div>

          <div class="bg-black/40 p-6 rounded-xl border border-white/5 shadow-2xl">
            <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-6 flex items-center gap-2">
              <Activity size={16} class="text-blue-400" />
              BPM Distribution
            </h3>
            <div class="flex items-end gap-2 h-48 pt-8">
              {#each [5, 12, 45, 80, 100, 60, 30, 10, 2] as val, i (i)}
                <div class="flex-1 bg-brand/20 hover:bg-brand/50 transition-colors rounded-t cursor-help relative group" style="height: {val}%">
                  <div class="absolute -top-6 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap">
                    {val} tracks
                  </div>
                </div>
              {/each}
            </div>
            <div class="flex justify-between mt-4 text-[10px] text-[#b3b3b3] font-mono">
              <span>90</span>
              <span>110</span>
              <span>128</span>
              <span>140</span>
              <span>160</span>
            </div>
          </div>
        </div>
      {/if}
    </div>

    <!-- Right Column: Inspector -->
    {#if showInspector}
      <div class="w-80 border-l border-white/5 bg-[#121212] overflow-y-auto shrink-0 flex flex-col">
        {#if selectedTrack}
          <div class="p-6 flex flex-col gap-6">
            <div class="aspect-square bg-[#282828] rounded-xl overflow-hidden shadow-2xl border border-white/10 group relative">
              {#if selectedTrack.cover}
                <img src={selectedTrack.cover} alt="" class="w-full h-full object-cover" />
              {:else}
                <div class="w-full h-full flex items-center justify-center">
                  <Music size={64} class="text-[#535353]" />
                </div>
              {/if}
              <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                 <button class="w-12 h-12 bg-brand rounded-full flex items-center justify-center text-black hover:scale-110 transition-transform">
                   <ChevronRight size={24} />
                 </button>
              </div>
            </div>

            <div class="flex flex-col gap-1">
              <h2 class="text-xl font-black text-white leading-tight">{selectedTrack.title}</h2>
              <p class="text-brand font-bold text-sm hover:underline cursor-pointer">{selectedTrack.artist}</p>
              <p class="text-[#b3b3b3] text-xs">{selectedTrack.label || 'Unknown Label'}</p>
            </div>

            <div class="grid grid-cols-2 gap-4">
              <div class="bg-white/5 p-3 rounded-lg border border-white/5">
                <span class="text-[9px] uppercase tracking-widest text-[#b3b3b3] block mb-1">BPM</span>
                <span class="text-lg font-black font-mono">{Math.round(selectedTrack.bpm) || '-'}</span>
              </div>
              <div class="bg-white/5 p-3 rounded-lg border border-white/5">
                <span class="text-[9px] uppercase tracking-widest text-[#b3b3b3] block mb-1">Key</span>
                <span class="text-lg font-black text-blue-400">{selectedTrack.key}</span>
              </div>
            </div>

            <div>
              <h3 class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold mb-3 flex items-center gap-2">
                <Activity size={14} class="text-brand" />
                Audio Features
              </h3>
              <div class="flex flex-col gap-3">
                <div class="flex flex-col gap-1">
                  <div class="flex justify-between text-[10px] mb-1">
                    <span class="text-[#b3b3b3]">Energy</span>
                    <span class="text-white font-mono">{Math.round(selectedTrack.energy)}%</span>
                  </div>
                  <div class="h-1 bg-white/5 rounded-full overflow-hidden">
                    <div class="h-full bg-brand" style="width: {selectedTrack.energy}%"></div>
                  </div>
                </div>
                <div class="flex flex-col gap-1">
                  <div class="flex justify-between text-[10px] mb-1">
                    <span class="text-[#b3b3b3]">Danceability</span>
                    <span class="text-white font-mono">{Math.round(selectedTrack.danceability)}%</span>
                  </div>
                  <div class="h-1 bg-white/5 rounded-full overflow-hidden">
                    <div class="h-full bg-brand" style="width: {selectedTrack.danceability}%"></div>
                  </div>
                </div>
                <div class="flex flex-col gap-1">
                  <div class="flex justify-between text-[10px] mb-1">
                    <span class="text-[#b3b3b3]">Popularity</span>
                    <span class="text-white font-mono">{selectedTrack.popularity}%</span>
                  </div>
                  <div class="h-1 bg-white/5 rounded-full overflow-hidden">
                    <div class="h-full bg-brand" style="width: {selectedTrack.popularity}%"></div>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h3 class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold mb-3">Tags</h3>
              <div class="flex flex-wrap gap-1">
                {#each ['Remix', 'Workout', 'Favorite', 'HQ'] as tag (tag)}
                  <span class="text-[10px] bg-[#242424] px-2 py-0.5 rounded border border-white/5 text-[#b3b3b3]">{tag}</span>
                {/each}
              </div>
            </div>

            <div>
               <h3 class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold mb-3 flex items-center gap-2">
                 <Mic2 size={14} class="text-brand" />
                 Lyrics
               </h3>
               <div class="bg-black/40 p-4 rounded-lg border border-white/5 max-h-40 overflow-y-auto text-xs text-[#b3b3b3] leading-relaxed italic">
                 {selectedTrack.lyrics}
               </div>
            </div>

            <div class="pt-4 border-t border-white/5 flex flex-col gap-2">
               <p class="text-[10px] text-[#535353] flex items-center gap-2"><Calendar size={12} /> Added: {selectedTrack.created_at || 'Unknown'}</p>
               <p class="text-[10px] text-[#535353] flex items-center gap-2"><Hash size={12} /> ID: {selectedTrack.id}</p>
            </div>
          </div>
        {:else}
          <div class="flex-1 flex flex-col items-center justify-center p-8 text-center text-[#b3b3b3] gap-4">
            <div class="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center">
              <Info size={32} />
            </div>
            <div>
              <h4 class="text-white font-bold mb-1">No Track Selected</h4>
              <p class="text-xs">Select a track from the library to view detailed metadata and analytics.</p>
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .no-scrollbar::-webkit-scrollbar {
    display: none;
  }
  .no-scrollbar {
    -ms-overflow-style: none;
    scrollbar-width: none;
  }
  
  :global(.text-brand) {
    color: #1DB954;
  }
  :global(.bg-brand) {
    background-color: #1DB954;
  }
  :global(.border-brand) {
    border-color: #1DB954;
  }
  :global(.accent-brand) {
    accent-color: #1DB954;
  }

  table thead th {
    font-size: 10px;
  }

  table tbody tr {
    height: 64px;
  }

  table tbody td {
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  }
</style>
