<script lang="ts">
  import { List, LayoutTemplate, Plus, Trash2, Music } from 'lucide-svelte';
  
  export let API_BASE: string;
  export let apiKey: string;
  export let users: any[];
  export let playlists: any[];
  export let selectedUser: any;
  export let getHeaders: () => any;
  export let fetchPlaylists: () => Promise<void>;
  export let onSelectUser: (user: any) => void;
  export let onMessage: (msg: string) => void;
  export let onError: (err: string) => void;

  let isPlaylistModalOpen = false;
  let isPlaylistTracksModalOpen = false;
  let playlistTracks: any[] = [];
  let viewingPlaylist: any = null;
  let editingPlaylist: any = null;
  let playlistName = '';
  let playlistParams: any = {}; // Changed to object

  let availableGenres: any[] = [];

  async function fetchGenres() {
    try {
      const res = await fetch(`${API_BASE}/api/rules`, { headers: getHeaders() });
      const data = await res.json();
      availableGenres = data.genres || [];
    } catch (err) {
      console.error("Failed to fetch genres:", err);
    }
  }

  function formatParams(paramsStr: string) {
    if (!paramsStr) return '-';
    try {
      const params = JSON.parse(paramsStr);
      let parts = [];
      if (params.song_type && params.song_type !== 'both') parts.push(params.song_type);
      if (params.genres && params.genres.length > 0) parts.push(params.genres.join(', '));
      if (params.rating_range) parts.push(`Rating: ${params.rating_range[0]}-${params.rating_range[1]}`);
      if (params.sort_method) parts.push(`Sort: ${params.sort_method}`);
      if (params.size) parts.push(`Size: ${params.size}`);
      
      if (parts.length > 0) return parts.join(' • ');
      
      // Fallback for old rules format
      if (params.rules) {
        return params.rules.map((r: any) => `${r.column}=${r.value}`).join(' • ');
      }
      return paramsStr;
    } catch(e) {
      if (paramsStr.includes('&')) return paramsStr.split('&').join(' • ');
      return paramsStr;
    }
  }

  async function fetchPlaylistTracks(playlist: any) {
    viewingPlaylist = playlist;
    playlistTracks = [];
    isPlaylistTracksModalOpen = true;
    if (!selectedUser) return;
    const user_id = selectedUser.id;
    try {
      const res = await fetch(`${API_BASE}/api/users/${user_id}/dynamic-playlists/${playlist.id}/tracks`, { headers: getHeaders() });
      playlistTracks = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function savePlaylist() {
    if (!selectedUser || !playlistName) return;
    try {
      const url = editingPlaylist 
        ? `${API_BASE}/api/users/${selectedUser.id}/dynamic-playlists/${editingPlaylist.id}`
        : `${API_BASE}/api/users/${selectedUser.id}/dynamic-playlists`;
      
      const response = await fetch(url, {
        method: editingPlaylist ? 'PUT' : 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          name: playlistName,
          params: JSON.stringify(playlistParams)
        })
      });

      if (response.ok) {
        onMessage(editingPlaylist ? 'Playlist bijgewerkt' : 'Playlist opgeslagen');
        isPlaylistModalOpen = false;
        fetchPlaylists();
      } else {
        onError("Kon playlist niet opslaan.");
      }
    } catch (err) {
      onError("Fout bij opslaan playlist.");
    }
  }

  async function deletePlaylist(id: number) {
    if (!selectedUser || !confirm('Weet je zeker dat je deze playlist wilt verwijderen?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/dynamic-playlists/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Playlist verwijderd.");
        fetchPlaylists();
      } else {
        onError("Kon playlist niet verwijderen.");
      }
    } catch (err) {
      onError("Fout bij verwijderen playlist.");
    }
  }

  function openPlaylistEditor(playlist: any = null) {
    editingPlaylist = playlist;
    if (playlist) {
      playlistName = playlist.name;
      try {
        playlistParams = JSON.parse(playlist.params);
      } catch (e) {
        playlistParams = { genres: [], rating_range: [0, 100], size: 500, sort_method: 'newest', song_type: 'both' };
      }
    } else {
      playlistName = '';
      playlistParams = { genres: [], rating_range: [0, 100], size: 500, sort_method: 'newest', song_type: 'both' };
    }
    fetchGenres();
    isPlaylistModalOpen = true;
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h2 class="text-4xl font-extrabold mb-2">🎵 Dynamic Playlists</h2>
      <div class="flex items-center gap-4">
        <p class="text-spotify-lightgray">Beheer de tiles en slimme afspeellijsten voor</p>
        <select 
          bind:value={selectedUser} 
          on:change={() => {
            if (selectedUser) {
              onSelectUser(selectedUser);
              fetchPlaylists();
            }
          }}
          class="bg-spotify-dark border border-spotify-gray rounded-full px-4 py-1 text-white text-sm focus:outline-none focus:border-spotify-green transition-colors"
        >
          <option value={null}>Selecteer gebruiker...</option>
          {#each users as user}
            <option value={user}>{user.username}</option>
          {/each}
        </select>
      </div>
    </div>
    <div class="flex gap-4">
      <button 
        on:click={() => {
          if (!selectedUser) {
            alert('Selecteer eerst een gebruiker');
            return;
          }
          if(confirm('Weet je zeker dat je de standaard playlists wilt herstellen voor deze gebruiker?')) {
            fetch(`${API_BASE}/api/users/${selectedUser.id}/dynamic-playlists/seed-defaults`, {
              method: 'POST',
              headers: { 'X-API-Key': apiKey }
            }).then(() => fetchPlaylists());
          }
        }}
        class="bg-spotify-gray text-white font-bold px-6 py-3 rounded-full hover:bg-spotify-lightgray transition-colors flex items-center gap-2"
      >
        <LayoutTemplate size={20} /> DEFAULTS
      </button>
      <button 
        on:click={() => openPlaylistEditor()}
        class="bg-spotify-green text-black font-extrabold px-8 py-3 rounded-full hover:scale-105 transition-transform flex items-center gap-2"
      >
        <Plus size={20} /> NIEUWE PLAYLIST
      </button>
    </div>
  </header>

  <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
    <table class="w-full text-left">
      <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
        <tr>
          <th class="p-4">Naam</th>
          <th class="p-4">Identifiers</th>
          <th class="p-4 text-right">Acties</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-spotify-gray divide-opacity-30">
        {#each playlists as playlist}
          <tr class="hover:bg-white hover:bg-opacity-5 transition-colors group">
            <td class="p-4 font-bold text-white">
              <div class="flex items-center gap-2">
                {playlist.name}
                {#if playlist.source}
                  <span class="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold 
                    {playlist.source === 'lms-alpha' ? 'bg-purple-600 text-white' : 
                     playlist.source === 'lms-stable' ? 'bg-spotify-green text-black' : 'bg-spotify-gray text-white'}">
                    {playlist.source.replace('lms-', '')}
                  </span>
                {/if}
              </div>
            </td>
            <td class="p-4 text-spotify-lightgray font-mono text-sm">
              {formatParams(playlist.params)}
            </td>
            <td class="p-4 text-right">
              <div class="flex items-center justify-end gap-2">
                <button 
                  on:click={() => fetchPlaylistTracks(playlist)}
                  class="p-2 text-spotify-lightgray hover:text-spotify-green transition-colors"
                  title="Tracks bekijken"
                >
                  <List size={18} />
                </button>
                <button 
                  on:click={() => openPlaylistEditor(playlist)}
                  class="p-2 text-spotify-lightgray hover:text-white transition-colors"
                  title="Bewerken"
                >
                  <Music size={18} />
                </button>
                <button 
                  on:click={() => deletePlaylist(playlist.id)}
                  class="p-2 text-spotify-lightgray hover:text-red-500 transition-colors"
                  title="Verwijderen"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </td>
          </tr>
        {/each}
        {#if playlists.length === 0}
          <tr>
            <td colspan="3" class="p-8 text-center text-spotify-lightgray italic">
              Geen dynamic playlists gevonden.
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>

<!-- Playlist Editor Modal -->
{#if isPlaylistModalOpen}
  <div class="fixed inset-0 bg-black bg-opacity-80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-spotify-gray w-full max-w-2xl rounded-2xl border border-white border-opacity-10 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
      <header class="p-6 border-b border-white border-opacity-5 flex justify-between items-center">
        <h3 class="text-2xl font-bold">{editingPlaylist ? 'Afspeellijst Bewerken' : 'Nieuwe Dynamic Playlist'}</h3>
        <button on:click={() => isPlaylistModalOpen = false} class="text-spotify-lightgray hover:text-white text-3xl">&times;</button>
      </header>
      <div class="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
        <div>
          <label class="block text-sm font-bold text-spotify-lightgray uppercase mb-2">Playlist Naam</label>
          <input 
            type="text" 
            bind:value={playlistName}
            placeholder="Bijv. Favorites, Hard Trance, etc."
            class="w-full bg-spotify-dark border border-white border-opacity-10 rounded-md p-3 text-white focus:outline-none focus:border-spotify-green transition-all"
          />
        </div>
        
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-bold text-spotify-lightgray uppercase mb-2">Type</label>
            <select 
              bind:value={playlistParams.song_type}
              class="w-full bg-spotify-dark border border-white border-opacity-10 rounded-md p-3 text-white focus:outline-none focus:border-spotify-green transition-all"
            >
              <option value="both">Alle (Tracks & Sets)</option>
              <option value="track">Alleen Tracks (&lt; 10 min)</option>
              <option value="set">Alleen Sets (&gt; 10 min)</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-bold text-spotify-lightgray uppercase mb-2">Maximum Grootte</label>
            <input 
              type="number" 
              bind:value={playlistParams.size}
              class="w-full bg-spotify-dark border border-white border-opacity-10 rounded-md p-3 text-white focus:outline-none focus:border-spotify-green transition-all"
            />
          </div>
        </div>

        <div>
          <label class="block text-sm font-bold text-spotify-lightgray uppercase mb-2">Genres</label>
          <div class="flex flex-wrap gap-2 max-h-32 overflow-y-auto p-2 bg-spotify-dark rounded-md border border-white border-opacity-10">
            {#each availableGenres as genre}
              <button 
                on:click={() => {
                  if (playlistParams.genres.includes(genre.name)) {
                    playlistParams.genres = playlistParams.genres.filter(g => g !== genre.name);
                  } else {
                    playlistParams.genres = [...playlistParams.genres, genre.name];
                  }
                }}
                class="px-3 py-1 rounded-full text-xs font-bold transition-colors 
                  {playlistParams.genres.includes(genre.name) ? 'bg-spotify-green text-black' : 'bg-spotify-gray text-spotify-lightgray hover:text-white'}"
              >
                {genre.name}
              </button>
            {/each}
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-bold text-spotify-lightgray uppercase mb-2">Sorteer op</label>
            <select 
              bind:value={playlistParams.sort_method}
              class="w-full bg-spotify-dark border border-white border-opacity-10 rounded-md p-3 text-white focus:outline-none focus:border-spotify-green transition-all"
            >
              <option value="newest">Nieuwste eerst</option>
              <option value="oldest">Oudste eerst</option>
              <option value="highest_rated">Hoogste rating</option>
              <option value="random">Willekeurig (Shuffle)</option>
            </select>
          </div>
          <div>
            <label class="block text-sm font-bold text-spotify-lightgray uppercase mb-2">Rating Bereik</label>
            <div class="flex items-center gap-2">
              <input 
                type="number" min="0" max="100"
                bind:value={playlistParams.rating_range[0]}
                class="w-16 bg-spotify-dark border border-white border-opacity-10 rounded-md p-3 text-white text-center"
              />
              <span class="text-spotify-lightgray">tot</span>
              <input 
                type="number" min="0" max="100"
                bind:value={playlistParams.rating_range[1]}
                class="w-16 bg-spotify-dark border border-white border-opacity-10 rounded-md p-3 text-white text-center"
              />
            </div>
          </div>
        </div>
      </div>
      <footer class="p-6 bg-black bg-opacity-20 flex justify-end gap-4">
        <button 
          on:click={() => isPlaylistModalOpen = false}
          class="px-6 py-2 text-white font-bold hover:underline"
        >
          ANNULEREN
        </button>
        <button 
          on:click={savePlaylist}
          class="bg-spotify-green text-black font-extrabold px-8 py-2 rounded-full hover:scale-105 transition-transform"
        >
          PLAYLIST OPSLAAN
        </button>
      </footer>
    </div>
  </div>
{/if}

<!-- Playlist Tracks Modal -->
{#if isPlaylistTracksModalOpen}
  <div class="fixed inset-0 bg-black bg-opacity-80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-spotify-gray w-full max-w-4xl h-[80vh] rounded-2xl border border-white border-opacity-10 shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
      <header class="p-6 border-b border-white border-opacity-5 flex justify-between items-center">
        <div>
          <h3 class="text-2xl font-bold">{viewingPlaylist?.name}</h3>
          <p class="text-spotify-lightgray text-sm">Preview van tracks gebaseerd op de dynamic rules.</p>
        </div>
        <button on:click={() => isPlaylistTracksModalOpen = false} class="text-spotify-lightgray hover:text-white text-3xl">&times;</button>
      </header>
      <div class="flex-1 overflow-y-auto">
        <table class="w-full text-left">
          <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray sticky top-0">
            <tr>
              <th class="p-4">Titel</th>
              <th class="p-4">Artiest</th>
              <th class="p-4">Genre</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-spotify-gray divide-opacity-30">
            {#each playlistTracks as track}
              <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                <td class="p-4 font-bold">{track.title}</td>
                <td class="p-4 text-spotify-lightgray">{track.artist}</td>
                <td class="p-4 text-spotify-lightgray text-sm">{track.genre || '-'}</td>
              </tr>
            {/each}
            {#if playlistTracks.length === 0}
              <tr>
                <td colspan="3" class="p-12 text-center text-spotify-lightgray italic">
                  Geen tracks gevonden die voldoen aan de regels.
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
      <footer class="p-6 bg-black bg-opacity-20 flex justify-end">
        <button 
          on:click={() => isPlaylistTracksModalOpen = false}
          class="bg-spotify-green text-black font-extrabold px-8 py-2 rounded-full hover:scale-105 transition-transform"
        >
          SLUITEN
        </button>
      </footer>
    </div>
  </div>
{/if}
