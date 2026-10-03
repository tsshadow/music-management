<script >
  import { t } from '../../i18n/index.js';
  import { notify } from '../../notifications.js';
  import { List, LayoutTemplate, Plus, Trash2, Music } from '@lucide/svelte';
  
  export let API_BASE;
  export let apiKey;
  export let users;
  export let playlists;
  export let selectedUser;
  export let getHeaders;
  export let fetchPlaylists;
  export let onSelectUser;
  export let onMessage;
  export let onError;

  let isPlaylistModalOpen = false;
  let isPlaylistTracksModalOpen = false;
  let playlistTracks = [];
  let viewingPlaylist = null;
  let editingPlaylist = null;
  let playlistName = '';
  let playlistParams = {}; // Changed to object

  let availableGenres = [];

  async function fetchGenres() {
    try {
      const res = await fetch(`${API_BASE}/api/rules`, { headers: getHeaders() });
      const data = await res.json();
      availableGenres = data.genres || [];
    } catch (err) {
      console.error("Failed to fetch genres:", err);
    }
  }

  function formatParams(paramsStr) {
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
        return params.rules.map((r) => `${r.column}=${r.value}`).join(' • ');
      }
      return paramsStr;
    } catch {
      if (paramsStr.includes('&')) return paramsStr.split('&').join(' • ');
      return paramsStr;
    }
  }

  async function fetchPlaylistTracks(playlist) {
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
        onMessage(editingPlaylist ? $t('management.playlists.updated') : $t('management.playlists.saved'));
        isPlaylistModalOpen = false;
        fetchPlaylists();
      } else {
        onError($t('management.playlists.saveFailed'));
      }
    } catch {
      onError($t('management.playlists.saveError'));
    }
  }

  async function deletePlaylist(id) {
    if (!selectedUser || !confirm($t('management.playlists.confirmDelete'))) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/dynamic-playlists/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.playlists.deleted'));
        fetchPlaylists();
      } else {
        onError($t('management.playlists.deleteFailed'));
      }
    } catch {
      onError($t('management.playlists.deleteError'));
    }
  }

  function openPlaylistEditor(playlist = null) {
    editingPlaylist = playlist;
    if (playlist) {
      playlistName = playlist.name;
      try {
        playlistParams = JSON.parse(playlist.params);
      } catch {
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
        <p class="text-muma-spotify-text">{$t('management.playlists.subtitle')}</p>
        <select 
          bind:value={selectedUser} 
          on:change={() => {
            if (selectedUser) {
              onSelectUser(selectedUser);
              fetchPlaylists();
            }
          }}
          class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-full px-4 py-1 text-white text-sm focus:outline-none focus:border-brand transition-colors"
        >
          <option value={null}>{$t('management.playlists.pickUser')}</option>
          {#each users as user (user.id)}
            <option value={user}>{user.username}</option>
          {/each}
        </select>
      </div>
    </div>
    <div class="flex gap-4">
      <button 
        on:click={() => {
          if (!selectedUser) {
            notify.warning($t('management.playlists.selectUserFirst'));
            return;
          }
          if(confirm($t('management.playlists.confirmRestoreDefaults'))) {
            fetch(`${API_BASE}/api/users/${selectedUser.id}/dynamic-playlists/seed-defaults`, {
              method: 'POST',
              headers: { 'X-API-Key': apiKey }
            }).then(() => fetchPlaylists());
          }
        }}
        class="bg-muma-spotify-panel text-white font-bold px-6 py-3 rounded-full hover:bg-muma-spotify-light transition-colors flex items-center gap-2"
      >
        <LayoutTemplate size={20} /> DEFAULTS
      </button>
      <button 
        on:click={() => openPlaylistEditor()}
        class="bg-brand text-black font-extrabold px-8 py-3 rounded-full hover:scale-105 transition-transform flex items-center gap-2"
      >
        <Plus size={20} /> {$t('management.playlists.new')}
      </button>
    </div>
  </header>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <table class="w-full text-left">
      <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text">
        <tr>
          <th class="p-4">{$t('management.libraries.name')}</th>
          <th class="p-4">{$t('management.playlists.identifiers')}</th>
          <th class="p-4 text-right">{$t('management.genres.actions')}</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-muma-spotify-panel/30">
        {#each playlists as playlist (playlist.id)}
          <tr class="hover:bg-white/5 transition-colors group">
            <td class="p-4 font-bold text-white">
              <div class="flex items-center gap-2">
                {playlist.name}
                {#if playlist.source}
                  <span class="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold 
                    {playlist.source.startsWith('server-') ? 'bg-brand text-black' : 
                      playlist.source.startsWith('lms-') ? 'bg-purple-600 text-white' : 'bg-muma-spotify-panel text-white'}">
                    {playlist.source.replace('server-', '').replace('lms-', '')}
                  </span>
                {/if}
              </div>
            </td>
            <td class="p-4 text-muma-spotify-text font-mono text-sm">
              {formatParams(playlist.params)}
            </td>
            <td class="p-4 text-right">
              <div class="flex items-center justify-end gap-2">
                <button 
                  on:click={() => fetchPlaylistTracks(playlist)}
                  class="p-2 text-muma-spotify-text hover:text-brand transition-colors"
                  title={$t('management.playlists.viewTracks')}
                >
                  <List size={18} />
                </button>
                <button 
                  on:click={() => openPlaylistEditor(playlist)}
                  class="p-2 text-muma-spotify-text hover:text-white transition-colors"
                  title={$t('common.edit')}
                >
                  <Music size={18} />
                </button>
                <button 
                  on:click={() => deletePlaylist(playlist.id)}
                  class="p-2 text-muma-spotify-text hover:text-red-500 transition-colors"
                  title={$t('common.remove')}
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </td>
          </tr>
        {/each}
        {#if playlists.length === 0}
          <tr>
            <td colspan="3" class="p-8 text-center text-muma-spotify-text italic">
              {$t('management.playlists.empty')}
            </td>
          </tr>
        {/if}
      </tbody>
    </table>
  </div>
</section>

<!-- Playlist Editor Modal -->
{#if isPlaylistModalOpen}
  <div class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-muma-spotify-panel w-full max-w-2xl rounded-2xl border border-white/10 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
      <header class="p-6 border-b border-white/5 flex justify-between items-center">
        <h3 class="text-2xl font-bold">{editingPlaylist ? $t('management.playlists.editTitle') : $t('management.playlists.newTitle')}</h3>
        <button on:click={() => isPlaylistModalOpen = false} class="text-muma-spotify-text hover:text-white text-3xl">&times;</button>
      </header>
      <div class="p-6 space-y-6 max-h-[60vh] overflow-y-auto">
        <div>
          <label for="playlistName" class="block text-sm font-bold text-muma-spotify-text uppercase mb-2">{$t('management.playlists.name')}</label>
          <input 
            id="playlistName"
            type="text" 
            bind:value={playlistName}
            placeholder={$t('management.playlists.namePlaceholder')}
            class="w-full bg-muma-spotify-dark border border-white/10 rounded-md p-3 text-white focus:outline-none focus:border-brand transition-all"
          />
        </div>
        
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label for="playlistType" class="block text-sm font-bold text-muma-spotify-text uppercase mb-2">{$t('management.playlists.type')}</label>
            <select 
              id="playlistType"
              bind:value={playlistParams.song_type}
              class="w-full bg-muma-spotify-dark border border-white/10 rounded-md p-3 text-white focus:outline-none focus:border-brand transition-all"
            >
              <option value="both">{$t('management.playlists.typeAll')}</option>
              <option value="track">{$t('management.playlists.typeTracks')}</option>
              <option value="set">{$t('management.playlists.typeSets')}</option>
            </select>
          </div>
          <div>
            <label for="playlistSize" class="block text-sm font-bold text-muma-spotify-text uppercase mb-2">{$t('management.playlists.maxSize')}</label>
            <input 
              id="playlistSize"
              type="number" 
              bind:value={playlistParams.size}
              class="w-full bg-muma-spotify-dark border border-white/10 rounded-md p-3 text-white focus:outline-none focus:border-brand transition-all"
            />
          </div>
        </div>

        <div>
          <span class="block text-sm font-bold text-muma-spotify-text uppercase mb-2">{$t('nav.genres')}</span>
          <div class="flex flex-wrap gap-2 max-h-32 overflow-y-auto p-2 bg-muma-spotify-dark rounded-md border border-white/10">
            {#each availableGenres as genre (genre.name)}
              <button 
                on:click={() => {
                  if (playlistParams.genres.includes(genre.name)) {
                    playlistParams.genres = playlistParams.genres.filter(g => g !== genre.name);
                  } else {
                    playlistParams.genres = [...playlistParams.genres, genre.name];
                  }
                }}
                class="px-3 py-1 rounded-full text-xs font-bold transition-colors 
                  {playlistParams.genres.includes(genre.name) ? 'bg-brand text-black' : 'bg-muma-spotify-panel text-muma-spotify-text hover:text-white'}"
              >
                {genre.name}
              </button>
            {/each}
          </div>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <label for="playlistSort" class="block text-sm font-bold text-muma-spotify-text uppercase mb-2">{$t('filter.sortBy')}</label>
            <select 
              id="playlistSort"
              bind:value={playlistParams.sort_method}
              class="w-full bg-muma-spotify-dark border border-white/10 rounded-md p-3 text-white focus:outline-none focus:border-brand transition-all"
            >
              <option value="newest">{$t('management.playlists.newestFirst')}</option>
              <option value="oldest">{$t('management.playlists.oldestFirst')}</option>
              <option value="highest_rated">{$t('management.playlists.highestRating')}</option>
              <option value="random">{$t('management.playlists.randomShuffle')}</option>
            </select>
          </div>
          <div>
            <span class="block text-sm font-bold text-muma-spotify-text uppercase mb-2">{$t('management.playlists.ratingRange')}</span>
            <div class="flex items-center gap-2">
              <input 
                type="number" min="0" max="100"
                bind:value={playlistParams.rating_range[0]}
                class="w-16 bg-muma-spotify-dark border border-white/10 rounded-md p-3 text-white text-center"
              />
              <span class="text-muma-spotify-text">{$t('management.playlists.rangeTo')}</span>
              <input 
                type="number" min="0" max="100"
                bind:value={playlistParams.rating_range[1]}
                class="w-16 bg-muma-spotify-dark border border-white/10 rounded-md p-3 text-white text-center"
              />
            </div>
          </div>
        </div>
      </div>
      <footer class="p-6 bg-black/20 flex justify-end gap-4">
        <button 
          on:click={() => isPlaylistModalOpen = false}
          class="px-6 py-2 text-white font-bold hover:underline"
        >
          {$t('management.playlists.cancelUpper')}
        </button>
        <button 
          on:click={savePlaylist}
          class="bg-brand text-black font-extrabold px-8 py-2 rounded-full hover:scale-105 transition-transform"
        >
          {$t('management.playlists.save')}
        </button>
      </footer>
    </div>
  </div>
{/if}

<!-- Playlist Tracks Modal -->
{#if isPlaylistTracksModalOpen}
  <div class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-muma-spotify-panel w-full max-w-4xl h-[80vh] rounded-2xl border border-white/10 shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
      <header class="p-6 border-b border-white/5 flex justify-between items-center">
        <div>
          <h3 class="text-2xl font-bold">{viewingPlaylist?.name}</h3>
          <p class="text-muma-spotify-text text-sm">{$t('management.playlists.previewHelp')}</p>
        </div>
        <button on:click={() => isPlaylistTracksModalOpen = false} class="text-muma-spotify-text hover:text-white text-3xl">&times;</button>
      </header>
      <div class="flex-1 overflow-y-auto">
        <table class="w-full text-left">
          <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text sticky top-0">
            <tr>
              <th class="p-4">{$t('track.title')}</th>
              <th class="p-4">{$t('common.artist')}</th>
              <th class="p-4">{$t('nav.genres')}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-muma-spotify-panel/30">
            {#each playlistTracks as track (track.id || track.path)}
              <tr class="hover:bg-white/5 transition-colors">
                <td class="p-4 font-bold">{track.title}</td>
                <td class="p-4 text-muma-spotify-text">{track.artist}</td>
                <td class="p-4 text-muma-spotify-text text-sm">{track.genre || '-'}</td>
              </tr>
            {/each}
            {#if playlistTracks.length === 0}
              <tr>
                <td colspan="3" class="p-12 text-center text-muma-spotify-text italic">
                  {$t('management.playlists.noMatchingTracks')}
                </td>
              </tr>
            {/if}
          </tbody>
        </table>
      </div>
      <footer class="p-6 bg-black/20 flex justify-end">
        <button 
          on:click={() => isPlaylistTracksModalOpen = false}
          class="bg-brand text-black font-extrabold px-8 py-2 rounded-full hover:scale-105 transition-transform"
        >
          {$t('management.playlists.closeUpper')}
        </button>
      </footer>
    </div>
  </div>
{/if}
