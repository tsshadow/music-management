<script>
  import { Search, Image, RefreshCw, User, Loader2, Link2, Upload, Trash2, X, Star } from '@lucide/svelte';
  import { SvelteSet } from 'svelte/reactivity';

  let {
    API_BASE,
    apiKey,
    getHeaders,
    fetchArtistImages,
    fetchProgress,
    imageStats,
    refreshStats = () => {},
    onMessage = () => {},
    onError = () => {}
  } = $props();

  const PAGE_SIZE = 60;

  let query = $state('');
  let filter = $state('all');
  let artists = $state([]);
  let total = $state(0);
  let searching = $state(false);
  let searchError = $state('');
  let hasSearched = $state(false);
  // Bumped after every mutation so the browser refetches an artist image whose URL
  // (keyed by artist name) did not change but whose bytes did.
  let cacheBust = $state(0);
  let busyArtistIds = new SvelteSet();
  let brokenArtistIds = new SvelteSet();

  let selected = $state(null);
  let selectedImages = $state([]);
  let selectedLoading = $state(false);

  let urlDialogArtist = $state(null);
  let imageUrlInput = $state('');
  let fileInput = $state(null);
  let uploadTargetId = $state(null);

  let debounceTimer;

  const progressPercent = $derived(
    fetchProgress.total > 0 ? Math.round((fetchProgress.current / fetchProgress.total) * 100) : 0
  );
  const canLoadMore = $derived(artists.length < total);

  function artistImageUrl(artist) {
    const version = artist.image_updated_at || artist.primary_image_id || '';
    return `${API_BASE}/api/artists/${encodeURIComponent(artist.name)}/image`
      + `?apiKey=${encodeURIComponent(apiKey)}&v=${encodeURIComponent(version)}-${cacheBust}`;
  }

  /**
   * Reads a JSON response, turning anything that is not a successful JSON payload
   * into a thrown Error. Without this an error body (e.g. `{"detail": "..."}`) would
   * silently flow into the list state and render as an empty page with no explanation.
   */
  async function readJson(res) {
    let body = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    if (!res.ok) {
      throw new Error(body?.detail || `${res.status} ${res.statusText || 'Request failed'}`);
    }
    return body;
  }

  async function runSearch({ append = false } = {}) {
    const offset = append ? artists.length : 0;
    searching = true;
    searchError = '';
    try {
      const params = new URLSearchParams({
        q: query,
        only: filter,
        limit: String(PAGE_SIZE),
        offset: String(offset)
      });
      const res = await fetch(`${API_BASE}/api/artists/manage/search?${params}`, { headers: getHeaders() });
      const body = await readJson(res);
      const items = Array.isArray(body?.items) ? body.items : [];
      artists = append ? [...artists, ...items] : items;
      total = Number.isFinite(body?.total) ? body.total : items.length;
      hasSearched = true;
    } catch (err) {
      searchError = err.message || String(err);
      hasSearched = true;
      if (!append) {
        artists = [];
        total = 0;
      }
    } finally {
      searching = false;
    }
  }

  function scheduleSearch() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => runSearch(), 250);
  }

  function setFilter(next) {
    filter = next;
    runSearch();
  }

  async function withBusy(artistId, fn) {
    busyArtistIds.add(artistId);
    try {
      return await fn();
    } catch (err) {
      onError(err.message || String(err));
      return null;
    } finally {
      busyArtistIds.delete(artistId);
    }
  }

  async function refreshArtist(artistId) {
    // Re-read just this artist so its card reflects the new image without
    // discarding the current result list or scroll position.
    const target = artists.find((a) => a.id === artistId) || selected;
    if (target) {
      const params = new URLSearchParams({ q: target.name, only: 'all', limit: String(PAGE_SIZE), offset: '0' });
      try {
        const res = await fetch(`${API_BASE}/api/artists/manage/search?${params}`, { headers: getHeaders() });
        const body = await readJson(res);
        const fresh = (Array.isArray(body?.items) ? body.items : []).find((a) => a.id === artistId);
        if (fresh) {
          artists = artists.map((a) => (a.id === artistId ? fresh : a));
          if (selected?.id === artistId) selected = fresh;
        }
      } catch {
        // A failed refresh is cosmetic: the mutation itself already succeeded.
      }
    }
    brokenArtistIds.delete(artistId);
    cacheBust += 1;
    refreshStats();
  }

  async function autoFetch(artist) {
    await withBusy(artist.id, async () => {
      const res = await fetch(`${API_BASE}/api/artists/${artist.id}/fetch-image`, {
        method: 'POST',
        headers: getHeaders()
      });
      await readJson(res);
      onMessage(`Zoeken naar afbeelding voor ${artist.name} gestart...`);
      setTimeout(() => refreshArtist(artist.id), 4000);
    });
  }

  async function clearImage(artist) {
    await withBusy(artist.id, async () => {
      const res = await fetch(`${API_BASE}/api/artists/${artist.id}/image/clear`, {
        method: 'POST',
        headers: getHeaders()
      });
      await readJson(res);
      onMessage(`Afbeelding van ${artist.name} verwijderd.`);
      await refreshArtist(artist.id);
      if (selected?.id === artist.id) await loadStoredImages(artist.id);
    });
  }

  function openUrlDialog(artist) {
    urlDialogArtist = artist;
    imageUrlInput = '';
  }

  async function saveImageUrl() {
    const artist = urlDialogArtist;
    if (!artist) return;
    const url = imageUrlInput.trim();
    if (!url) return;
    urlDialogArtist = null;
    await withBusy(artist.id, async () => {
      const res = await fetch(`${API_BASE}/api/artists/${artist.id}/image/url`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ url })
      });
      await readJson(res);
      onMessage(`Afbeelding voor ${artist.name} opgeslagen.`);
      await refreshArtist(artist.id);
    });
  }

  function pickFile(artist) {
    uploadTargetId = artist.id;
    fileInput?.click();
  }

  async function onFileChosen(event) {
    const file = event.target.files?.[0];
    const artistId = uploadTargetId;
    event.target.value = '';
    if (!file || !artistId) return;
    const artist = artists.find((a) => a.id === artistId) || selected;
    await withBusy(artistId, async () => {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(new Error('Kon bestand niet lezen'));
        reader.readAsDataURL(file);
      });
      const res = await fetch(`${API_BASE}/api/artists/${artistId}/image/upload`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ filename: file.name, data })
      });
      await readJson(res);
      onMessage(`Afbeelding voor ${artist?.name ?? 'artiest'} geüpload.`);
      await refreshArtist(artistId);
    });
  }

  async function openArtist(artist) {
    selected = artist;
    await loadStoredImages(artist.id);
  }

  async function loadStoredImages(artistId) {
    selectedLoading = true;
    selectedImages = [];
    try {
      const res = await fetch(`${API_BASE}/api/artists/${artistId}/images`, { headers: getHeaders() });
      const body = await readJson(res);
      selectedImages = Array.isArray(body?.images) ? body.images : [];
    } catch (err) {
      onError(err.message || String(err));
    } finally {
      selectedLoading = false;
    }
  }

  async function makePrimary(artistId, imageId) {
    await withBusy(artistId, async () => {
      const res = await fetch(`${API_BASE}/api/artists/${artistId}/image/select/${imageId}`, {
        method: 'POST',
        headers: getHeaders()
      });
      await readJson(res);
      onMessage('Primaire afbeelding gewijzigd.');
      await refreshArtist(artistId);
      await loadStoredImages(artistId);
    });
  }

  $effect(() => {
    // First open of the tab: show something useful before anything is typed.
    if (!hasSearched && !searching) runSearch();
  });
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') { selected = null; urlDialogArtist = null; } }} />

<input type="file" accept="image/*" class="hidden" bind:this={fileInput} onchange={onFileChosen} />

<section class="space-y-8 animate-in fade-in duration-500">
  <header class="flex flex-col md:flex-row md:items-end justify-between gap-6">
    <div>
      <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">Artist Images</h1>
      <p class="text-spotify-lightgray text-lg">Zoek een artiest, bekijk de afbeelding en beheer hem handmatig.</p>
    </div>

    <div class="flex items-center gap-4">
      <div class="text-right">
        <p class="text-xs text-spotify-lightgray uppercase tracking-widest font-bold">Bibliotheek Status</p>
        <p class="text-2xl font-black text-white">
          <span class="text-spotify-green">{imageStats.artists_with_images}</span>
          <span class="text-spotify-lightgray mx-1">/</span>
          {imageStats.total_artists} <span class="text-sm font-normal text-spotify-lightgray">artiesten</span>
        </p>
      </div>

      <button
        onclick={fetchArtistImages}
        disabled={fetchProgress.active}
        class="bg-white text-black font-extrabold px-6 py-3 rounded-full hover:scale-105 active:scale-95 transition-all flex items-center gap-2 shadow-xl shadow-white/5 disabled:opacity-50 disabled:scale-100"
      >
        {#if fetchProgress.active}
          <Loader2 size={20} class="animate-spin" />
          SCANNEN...
        {:else}
          <RefreshCw size={20} />
          RESCAN
        {/if}
      </button>
    </div>
  </header>

  {#if fetchProgress.active || fetchProgress.status === 'completed'}
    <div class="bg-spotify-gray bg-opacity-40 p-6 rounded-2xl border border-white border-opacity-10 shadow-2xl animate-in slide-in-from-top-4 duration-500">
      <div class="flex justify-between items-center mb-4">
        <div class="flex items-center gap-3">
          <div class="bg-spotify-green bg-opacity-20 p-2 rounded-lg">
            <RefreshCw size={20} class="text-spotify-green {fetchProgress.active ? 'animate-spin' : ''}" />
          </div>
          <div>
            <h3 class="font-bold text-lg">
              {fetchProgress.active ? 'Artist Images Scannen...' : 'Scan Voltooid!'}
            </h3>
            {#if fetchProgress.active && fetchProgress.last_artist}
              <p class="text-sm text-spotify-lightgray">Bezig met: <span class="text-white font-medium">{fetchProgress.last_artist}</span></p>
            {/if}
          </div>
        </div>
        <div class="text-right">
          <span class="text-2xl font-black text-spotify-green">{progressPercent}%</span>
          <p class="text-xs text-spotify-lightgray font-bold">{fetchProgress.current} / {fetchProgress.total}</p>
        </div>
      </div>

      <div class="w-full bg-black bg-opacity-40 h-3 rounded-full overflow-hidden border border-white border-opacity-5">
        <div class="h-full bg-gradient-to-r from-spotify-green to-emerald-400 transition-all duration-500 ease-out relative" style="width: {progressPercent}%">
          <div class="absolute inset-0 bg-white bg-opacity-20 animate-pulse"></div>
        </div>
      </div>
    </div>
  {/if}

  <div class="space-y-6">
    <div class="flex flex-col lg:flex-row lg:items-center gap-4">
      <div class="relative group flex-1 max-w-xl">
        <div class="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none text-spotify-lightgray group-focus-within:text-spotify-green transition-colors">
          {#if searching}
            <Loader2 size={20} class="animate-spin" />
          {:else}
            <Search size={20} />
          {/if}
        </div>
        <input
          type="text"
          bind:value={query}
          oninput={scheduleSearch}
          placeholder="Zoek artiest..."
          class="w-full bg-spotify-gray bg-opacity-50 border border-white border-opacity-10 rounded-full py-4 pl-12 pr-4 text-white focus:outline-none focus:border-spotify-green focus:bg-opacity-80 transition-all placeholder:text-spotify-lightgray text-lg shadow-lg"
        />
      </div>

      <div class="flex items-center gap-2">
        {#each [['all', 'Alle'], ['with', 'Met afbeelding'], ['without', 'Zonder afbeelding']] as [value, label] (value)}
          <button
            onclick={() => setFilter(value)}
            class="px-4 py-2 rounded-full text-sm font-bold transition-all border {filter === value ? 'bg-spotify-green text-black border-spotify-green' : 'bg-spotify-gray bg-opacity-40 text-spotify-lightgray border-white border-opacity-10 hover:text-white'}"
          >
            {label}
          </button>
        {/each}
      </div>
    </div>

    {#if searchError}
      <div class="bg-red-900 bg-opacity-40 border border-red-500 border-opacity-40 text-red-200 p-4 rounded-xl flex items-center justify-between gap-4">
        <span>Zoeken mislukt: {searchError}</span>
        <button onclick={() => runSearch()} class="font-bold underline shrink-0">Opnieuw</button>
      </div>
    {/if}

    {#if artists.length > 0}
      <p class="text-sm text-spotify-lightgray">{artists.length} van {total} artiesten</p>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6">
        {#each artists as artist (artist.id)}
          <div class="bg-spotify-gray bg-opacity-30 rounded-xl overflow-hidden border border-white border-opacity-5 hover:bg-opacity-50 transition-all group shadow-lg flex flex-col">
            <button
              type="button"
              onclick={() => openArtist(artist)}
              class="aspect-square bg-black flex items-center justify-center overflow-hidden relative w-full"
              title="Beheer afbeeldingen van {artist.name}"
            >
              {#if artist.has_image && !brokenArtistIds.has(artist.id)}
                <img
                  src={artistImageUrl(artist)}
                  alt={artist.name}
                  class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500"
                  onerror={() => brokenArtistIds.add(artist.id)}
                />
              {:else}
                <div class="flex flex-col items-center justify-center gap-2 text-spotify-lightgray opacity-40">
                  <User size={40} />
                  <span class="text-xs">Geen afbeelding</span>
                </div>
              {/if}
              {#if busyArtistIds.has(artist.id)}
                <div class="absolute inset-0 bg-black bg-opacity-60 flex items-center justify-center">
                  <Loader2 size={28} class="animate-spin text-spotify-green" />
                </div>
              {/if}
            </button>

            <div class="p-4 flex-1 flex flex-col gap-3">
              <div>
                <h3 class="font-bold truncate text-lg" title={artist.name}>{artist.name}</h3>
                <p class="text-xs text-spotify-lightgray mt-1">
                  {#if artist.has_image}
                    {artist.width}x{artist.height} • {artist.source || 'onbekend'}
                  {:else}
                    <span class={artist.image_status === 'failed' ? 'text-red-400' : ''}>
                      {artist.image_status === 'failed' ? 'Niet gevonden' : 'Geen afbeelding'}
                    </span>
                  {/if}
                </p>
              </div>

              <div class="flex items-center gap-1 mt-auto">
                <button onclick={() => autoFetch(artist)} disabled={busyArtistIds.has(artist.id)} title="Automatisch zoeken" class="p-2 rounded-lg bg-white bg-opacity-5 hover:bg-spotify-green hover:text-black transition-all disabled:opacity-40">
                  <RefreshCw size={16} />
                </button>
                <button onclick={() => pickFile(artist)} disabled={busyArtistIds.has(artist.id)} title="Bestand uploaden" class="p-2 rounded-lg bg-white bg-opacity-5 hover:bg-spotify-green hover:text-black transition-all disabled:opacity-40">
                  <Upload size={16} />
                </button>
                <button onclick={() => openUrlDialog(artist)} disabled={busyArtistIds.has(artist.id)} title="Afbeelding via URL" class="p-2 rounded-lg bg-white bg-opacity-5 hover:bg-spotify-green hover:text-black transition-all disabled:opacity-40">
                  <Link2 size={16} />
                </button>
                {#if artist.has_image}
                  <button onclick={() => clearImage(artist)} disabled={busyArtistIds.has(artist.id)} title="Afbeelding verwijderen" class="p-2 rounded-lg bg-white bg-opacity-5 hover:bg-red-500 hover:text-white transition-all disabled:opacity-40 ml-auto">
                    <Trash2 size={16} />
                  </button>
                {/if}
              </div>
            </div>
          </div>
        {/each}
      </div>

      {#if canLoadMore}
        <div class="flex justify-center">
          <button
            onclick={() => runSearch({ append: true })}
            disabled={searching}
            class="bg-white bg-opacity-10 hover:bg-opacity-20 px-6 py-3 rounded-full font-bold transition-all disabled:opacity-40"
          >
            Meer laden
          </button>
        </div>
      {/if}
    {:else if !searching && !searchError}
      <div class="bg-spotify-gray bg-opacity-20 p-12 rounded-xl text-center border border-dashed border-white border-opacity-10">
        <Search size={48} class="mx-auto mb-4 text-spotify-lightgray opacity-20" />
        <p class="text-spotify-lightgray text-xl font-medium">
          {#if query}
            Geen artiesten gevonden met de naam "{query}"
          {:else}
            Geen artiesten gevonden voor dit filter.
          {/if}
        </p>
      </div>
    {/if}
  </div>
</section>

{#if urlDialogArtist}
  <div class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4">
    <div class="bg-spotify-gray rounded-2xl border border-white border-opacity-10 p-6 w-full max-w-lg space-y-4 shadow-2xl">
      <div class="flex items-center justify-between">
        <h3 class="text-xl font-bold">Afbeelding via URL — {urlDialogArtist.name}</h3>
        <button onclick={() => (urlDialogArtist = null)} class="p-1 hover:text-spotify-green"><X size={20} /></button>
      </div>
      <input
        type="url"
        bind:value={imageUrlInput}
        placeholder="https://..."
        class="w-full bg-black bg-opacity-40 border border-white border-opacity-10 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-spotify-green"
      />
      <div class="flex justify-end gap-2">
        <button onclick={() => (urlDialogArtist = null)} class="px-4 py-2 rounded-full font-bold bg-white bg-opacity-10 hover:bg-opacity-20">Annuleren</button>
        <button onclick={saveImageUrl} disabled={!imageUrlInput.trim()} class="px-4 py-2 rounded-full font-bold bg-spotify-green text-black disabled:opacity-40">Opslaan</button>
      </div>
    </div>
  </div>
{/if}

{#if selected}
  <div class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-40 p-4">
    <div class="bg-spotify-gray rounded-2xl border border-white border-opacity-10 p-6 w-full max-w-3xl space-y-6 shadow-2xl max-h-[90vh] overflow-y-auto">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h3 class="text-2xl font-black">{selected.name}</h3>
          <p class="text-sm text-spotify-lightgray">
            {selected.has_image ? `${selected.width}x${selected.height} • bron: ${selected.source || 'onbekend'}` : 'Nog geen primaire afbeelding'}
          </p>
        </div>
        <button onclick={() => (selected = null)} class="p-1 hover:text-spotify-green"><X size={22} /></button>
      </div>

      <div class="flex flex-col sm:flex-row gap-6">
        <div class="w-48 h-48 shrink-0 bg-black rounded-xl overflow-hidden flex items-center justify-center">
          {#if selected.has_image && !brokenArtistIds.has(selected.id)}
            <img src={artistImageUrl(selected)} alt={selected.name} class="w-full h-full object-cover" />
          {:else}
            <User size={48} class="text-spotify-lightgray opacity-40" />
          {/if}
        </div>

        <div class="flex-1 space-y-3">
          <div class="flex flex-wrap gap-2">
            <button onclick={() => autoFetch(selected)} class="px-4 py-2 rounded-full font-bold bg-white bg-opacity-10 hover:bg-opacity-20 flex items-center gap-2"><RefreshCw size={16} /> Automatisch zoeken</button>
            <button onclick={() => pickFile(selected)} class="px-4 py-2 rounded-full font-bold bg-white bg-opacity-10 hover:bg-opacity-20 flex items-center gap-2"><Upload size={16} /> Uploaden</button>
            <button onclick={() => openUrlDialog(selected)} class="px-4 py-2 rounded-full font-bold bg-white bg-opacity-10 hover:bg-opacity-20 flex items-center gap-2"><Link2 size={16} /> URL</button>
            {#if selected.has_image}
              <button onclick={() => clearImage(selected)} class="px-4 py-2 rounded-full font-bold bg-white bg-opacity-10 hover:bg-red-500 flex items-center gap-2"><Trash2 size={16} /> Verwijderen</button>
            {/if}
          </div>

          <div>
            <h4 class="font-bold mb-2 flex items-center gap-2"><Image size={16} /> Opgeslagen afbeeldingen</h4>
            {#if selectedLoading}
              <p class="text-sm text-spotify-lightgray">Laden...</p>
            {:else if selectedImages.length === 0}
              <p class="text-sm text-spotify-lightgray">Nog niets opgeslagen voor deze artiest.</p>
            {:else}
              <ul class="space-y-2">
                {#each selectedImages as image (image.id)}
                  <li class="flex items-center justify-between gap-3 bg-black bg-opacity-30 rounded-lg px-3 py-2">
                    <div class="text-sm min-w-0">
                      <p class="font-bold truncate">
                        {image.source || 'onbekend'}
                        {#if image.is_primary}<span class="text-spotify-green ml-1">• primair</span>{/if}
                      </p>
                      <p class="text-xs text-spotify-lightgray truncate">
                        {image.width}x{image.height} • betrouwbaarheid {image.confidence}
                        {#if !image.exists_on_disk}<span class="text-red-400"> • bestand ontbreekt</span>{/if}
                      </p>
                    </div>
                    {#if !image.is_primary}
                      <button onclick={() => makePrimary(selected.id, image.id)} class="shrink-0 px-3 py-1 rounded-full text-xs font-bold bg-white bg-opacity-10 hover:bg-spotify-green hover:text-black flex items-center gap-1">
                        <Star size={14} /> Primair
                      </button>
                    {/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </div>
        </div>
      </div>
    </div>
  </div>
{/if}
