<script lang="ts">
  import { onMount } from 'svelte';
  import { Music, Search, RefreshCcw, ChevronLeft, ChevronRight, Download } from 'lucide-svelte';

  export let API_BASE: string;
  export let getHeaders: () => any;
  export let onMessage: (m: string) => void;
  export let onError: (e: string) => void;

  let tracks: any[] = [];
  let total = 0;
  let page = 1;
  let limit = 50;
  let searchQuery = "";
  let loading = false;
  let searchTimeout: any;
  let taggerBusy = false;
  let taggerStatusInterval: any;

  async function checkTaggerStatus() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/health`, {
        headers: getHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        taggerBusy = data.busy;
      }
    } catch (err) {
      console.error("Fout bij ophalen tagger status", err);
    }
  }

  async function tagAll() {
    if (!confirm("Weet je zeker dat je alle tracks in de bibliotheek opnieuw wilt taggen? Dit kan enige tijd duren.")) return;
    try {
      const res = await fetch(`${API_BASE}/api/tagger/tag/all`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Volledige scan gestart in de achtergrond.");
        taggerBusy = true;
      } else {
        const data = await res.json();
        onError(data.detail || "Fout bij starten volledige scan.");
      }
    } catch (err) {
      onError("Netwerkfout bij starten volledige scan.");
    }
  }

  async function stopTagging() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/tag/stop`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Stopverzoek verzonden naar de tagger.");
      }
    } catch (err) {
      onError("Netwerkfout bij stoppen tagger.");
    }
  }

  async function fetchTracks() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/library/tracks?q=${searchQuery}&page=${page}&limit=${limit}`, {
        headers: getHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        tracks = data.tracks;
        total = data.total;
      }
    } catch (err) {
      console.error(err);
      onError("Kon bibliotheek niet laden.");
    } finally {
      loading = false;
    }
  }

  function handleSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      page = 1;
      fetchTracks();
    }, 500);
  }

  async function rerunParse(track: any) {
    if (!confirm(`Weet je zeker dat je de analyse voor '${track.title}' opnieuw wilt uitvoeren?`)) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/library/tracks/${track.id}/rerun-parse`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage(`Scan voor '${track.title}' gestart.`);
      } else {
        const data = await res.json();
        onError(data.detail || "Fout bij starten scan.");
      }
    } catch (err) {
      onError("Netwerkfout bij starten scan.");
    }
  }

  async function redownload(track: any) {
    const url = track.sc_url || track.yt_url;
    if (!confirm(`Weet je zeker dat je '${track.title}' opnieuw wilt downloaden van ${url}?`)) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/library/tracks/${track.id}/redownload`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage(`Redownload voor '${track.title}' gestart in de achtergrond.`);
      } else {
        const data = await res.json();
        onError(data.detail || "Fout bij starten redownload.");
      }
    } catch (err) {
      onError("Netwerkfout bij starten redownload.");
    }
  }

  function nextPage() {
    if (page * limit < total) {
      page++;
      fetchTracks();
    }
  }

  function prevPage() {
    if (page > 1) {
      page--;
      fetchTracks();
    }
  }

  onMount(() => {
    fetchTracks();
    checkTaggerStatus();
    taggerStatusInterval = setInterval(checkTaggerStatus, 5000);
    return () => clearInterval(taggerStatusInterval);
  });
</script>

<div class="flex flex-col gap-8">
  <div class="flex justify-between items-end">
    <div>
      <h1 class="text-4xl font-black mb-2 flex items-center gap-4">
        <Music size={40} class="text-spotify-green" />
        Bibliotheek
      </h1>
      <p class="text-spotify-lightgray">Blader door alle tracks in de database en beheer metadata.</p>
    </div>
    
    <div class="flex gap-4">
      {#if taggerBusy}
        <button 
          on:click={stopTagging}
          class="bg-red-600 text-white font-bold py-2.5 px-6 rounded-full hover:scale-105 transition-all text-sm uppercase tracking-wider flex items-center gap-2"
        >
          <span class="w-2 h-2 bg-white rounded-full animate-pulse"></span>
          Stop Scan
        </button>
      {:else}
        <button 
          on:click={tagAll}
          class="border border-white border-opacity-20 text-white font-bold py-2.5 px-6 rounded-full hover:bg-white hover:text-black transition-all text-sm uppercase tracking-wider"
        >
          Scan All
        </button>
      {/if}
      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 text-spotify-lightgray" size={18} />
        <input 
          type="text" 
          bind:value={searchQuery} 
          on:input={handleSearch}
          placeholder="Zoek op titel, artiest of label..."
          class="bg-spotify-gray border-none rounded-full py-2.5 pl-10 pr-4 text-sm w-80 focus:ring-2 focus:ring-spotify-green transition-all"
        />
      </div>
      <button 
        on:click={fetchTracks}
        class="bg-white text-black font-bold py-2.5 px-6 rounded-full hover:scale-105 transition-all text-sm uppercase tracking-wider"
      >
        Vernieuwen
      </button>
    </div>
  </div>

  <div class="bg-black bg-opacity-40 rounded-xl overflow-hidden border border-white border-opacity-10">
    <table class="w-full text-left text-sm border-collapse">
      <thead>
        <tr class="text-spotify-lightgray border-b border-white border-opacity-10 uppercase text-[10px] tracking-widest font-bold">
          <th class="px-6 py-4">Titel</th>
          <th class="px-6 py-4">Artiest</th>
          <th class="px-6 py-4">Label</th>
          <th class="px-6 py-4">Genre</th>
          <th class="px-6 py-4">BPM</th>
          <th class="px-6 py-4">Acties</th>
        </tr>
      </thead>
      <tbody>
        {#if loading && tracks.length === 0}
          <tr>
            <td colspan="6" class="px-6 py-20 text-center text-spotify-lightgray">Laden...</td>
          </tr>
        {:else if tracks.length === 0}
          <tr>
            <td colspan="6" class="px-6 py-20 text-center text-spotify-lightgray">Geen tracks gevonden.</td>
          </tr>
        {:else}
          {#each tracks as track}
            <tr class="border-b border-white border-opacity-5 hover:bg-white hover:bg-opacity-5 transition-colors group">
              <td class="px-6 py-3">
                <div class="flex flex-col">
                  <span class="font-bold text-white group-hover:text-spotify-green transition-colors">{track.title}</span>
                  <span class="text-[10px] text-spotify-lightgray truncate max-w-xs" title={track.file_path}>
                    {track.file_path?.split('/').pop()}
                  </span>
                </div>
              </td>
              <td class="px-6 py-3 text-spotify-lightgray">{track.artist || '-'}</td>
              <td class="px-6 py-3 text-spotify-lightgray">{track.label || '-'}</td>
              <td class="px-6 py-3">
                <div class="flex flex-col gap-1">
                  {#if track.genre}
                    <span class="text-white text-[10px]">{track.genre}</span>
                  {/if}
                  {#if track.ml_genre}
                    <span class="bg-spotify-green bg-opacity-20 text-spotify-green px-2 py-0.5 rounded text-[10px] font-bold self-start">
                      {track.ml_genre}
                    </span>
                  {/if}
                  {#if !track.genre && !track.ml_genre}
                    <span class="text-spotify-lightgray">-</span>
                  {/if}
                </div>
              </td>
              <td class="px-6 py-3 text-spotify-lightgray">{track.bpm ? Math.round(track.bpm) : '-'}</td>
              <td class="px-6 py-3">
                <div class="flex gap-2">
                  <button 
                    on:click={() => rerunParse(track)}
                    class="text-spotify-lightgray hover:text-white transition-colors p-1"
                    title="Analyseer opnieuw"
                  >
                    <RefreshCcw size={18} />
                  </button>
                  {#if track.sc_url || track.yt_url}
                    <button 
                      on:click={() => redownload(track)}
                      class="text-spotify-lightgray hover:text-spotify-green transition-colors p-1"
                      title="Opnieuw downloaden van bron"
                    >
                      <Download size={18} />
                    </button>
                  {/if}
                </div>
              </td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>

    <!-- Pagination -->
    <div class="px-6 py-4 flex justify-between items-center bg-black bg-opacity-20">
      <div class="text-xs text-spotify-lightgray">
        Toon {tracks.length} van {total} tracks
      </div>
      <div class="flex gap-2">
        <button 
          on:click={prevPage} 
          disabled={page === 1}
          class="p-2 rounded-full hover:bg-spotify-gray disabled:opacity-30 transition-colors"
        >
          <ChevronLeft size={20} />
        </button>
        <span class="flex items-center px-4 font-bold text-sm">
          Pagina {page} van {Math.ceil(total / limit) || 1}
        </span>
        <button 
          on:click={nextPage} 
          disabled={page * limit >= total}
          class="p-2 rounded-full hover:bg-spotify-gray disabled:opacity-30 transition-colors"
        >
          <ChevronRight size={20} />
        </button>
      </div>
    </div>
  </div>
</div>
