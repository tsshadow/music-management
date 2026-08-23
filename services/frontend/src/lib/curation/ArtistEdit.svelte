<script>
  /**
   * Editing one artist: identity (MBID, external ids, aliases) and genre rules.
   *
   * Reached from the artist view, which knows the artist by an LMS id. MuMa knows it
   * by name -- the rule tables are keyed on the name, and the two id spaces have
   * nothing to do with each other -- so this page takes the name as its argument and
   * the artist view hands it over.
   */
  import { onMount } from 'svelte';

  import { authParams } from '../store.js';
  import ChipEditor from './ChipEditor.svelte';
  import CurationShell from './CurationShell.svelte';
  import GenreRuleEditor from './GenreRuleEditor.svelte';
  import { EXTERNAL_SOURCES, isMbid, mbidUrl } from './curation.js';
  import {
    addArtistAlias,
    addArtistGenre,
    loadArtist,
    loadWhiteGenres,
    removeArtistAlias,
    removeArtistExternalId,
    removeArtistGenre,
    retag,
    setArtistExternalId,
    setArtistMbid
  } from './curationApi.js';

  let { artistId, onback } = $props();

  /**
   * The name MuMa knows this artist by.
   *
   * `artistId` is an LMS id and means nothing to the MuMa API, so it is traded for a
   * name first. Doing that here rather than taking the name as a prop keeps the URL
   * bookmarkable: a refresh on /artist/123/edit has only the id to work from.
   */
  let name = $state('');
  let artist = $state(null);
  let whiteGenres = $state([]);
  let error = $state(null);
  let message = $state(null);
  let busy = $state(false);
  let mbidDraft = $state('');
  let newSource = $state(EXTERNAL_SOURCES[0]);
  let newExternalId = $state('');

  const mbidValid = $derived(isMbid(mbidDraft));
  const mbidLink = $derived(mbidUrl('artist', artist?.mbid));

  async function refresh() {
    artist = await loadArtist(name);
    mbidDraft = artist.mbid || '';
  }

  /** Runs one write, then reloads, so the page never shows a guess at the new state. */
  async function act(operation, confirmation) {
    error = null;
    message = null;
    busy = true;
    try {
      const result = await operation();
      await refresh();
      message = typeof confirmation === 'function' ? confirmation(result) : confirmation;
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }

  async function resolveName() {
    const response = await fetch(`/rest/getArtist?id=${artistId}&${$authParams}`);
    const data = await response.json();
    const resolved = data['subsonic-response']?.artist?.name;
    if (!resolved) throw new Error('Deze artiest bestaat niet meer in de bibliotheek.');
    name = resolved;
  }

  onMount(async () => {
    try {
      await resolveName();
      const [, genres] = await Promise.all([refresh(), loadWhiteGenres()]);
      whiteGenres = genres;
    } catch (e) {
      error = e.message;
    }
  });
</script>

{#if artist}
  <CurationShell
    title={artist.name}
    subtitle={artist.in_library
      ? `${artist.track_count} tracks in de bibliotheek`
      : 'Nog niet in de bibliotheek — regels kunnen alvast worden vastgelegd'}
    {error}
    {message}
    {onback}
  >
    <section>
      <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">MusicBrainz</h2>
      <p class="text-xs text-muma-spotify-text mt-1 mb-0">
        De MBID koppelt deze artiest aan MusicBrainz. Leeg laten wist de koppeling.
      </p>
      <div class="flex gap-2 mt-3">
        <input
          class="flex-1 bg-muma-spotify-light border-none rounded px-3 py-2 text-sm text-white font-mono"
          placeholder="00000000-0000-0000-0000-000000000000"
          bind:value={mbidDraft}
          disabled={!artist.in_library}
        />
        <button
          class="bg-brand text-black font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
          disabled={!mbidValid || busy || !artist.in_library}
          onclick={() => act(() => setArtistMbid(name, mbidDraft.trim() || null), 'MBID opgeslagen.')}
        >
          Opslaan
        </button>
      </div>
      {#if !mbidValid}
        <p class="text-xs text-red-400 mt-2 mb-0">
          Dat is geen MBID. Plak alleen het id, niet de hele MusicBrainz-URL.
        </p>
      {/if}
      {#if mbidLink}
        <a class="text-xs text-brand mt-2 inline-block" href={mbidLink} target="_blank" rel="noreferrer">
          Openen op MusicBrainz
        </a>
      {/if}
    </section>

    <section>
      <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">Externe ids</h2>
      <div class="flex flex-col gap-2 mt-3">
        {#each artist.external_ids as entry (entry.source)}
          <div class="flex items-center gap-3 bg-muma-spotify-light rounded px-3 py-2 text-sm">
            <span class="font-bold w-28">{entry.source}</span>
            <span class="flex-1 font-mono truncate">{entry.external_id}</span>
            {#if entry.verified}
              <span class="text-[11px] text-brand font-bold">geverifieerd</span>
            {/if}
            <button
              class="bg-transparent border-none text-muma-spotify-text hover:text-white cursor-pointer text-xs"
              onclick={() => act(() => removeArtistExternalId(name, entry.source), 'Id verwijderd.')}
            >
              Verwijderen
            </button>
          </div>
        {:else}
          <span class="text-sm text-muma-spotify-text">Nog geen externe ids.</span>
        {/each}
      </div>
      {#if artist.in_library}
        <div class="flex gap-2 mt-3">
          <select
            class="bg-muma-spotify-light border-none rounded px-3 py-2 text-sm text-white"
            bind:value={newSource}
            aria-label="Bron kiezen"
          >
            {#each EXTERNAL_SOURCES as source (source)}
              <option value={source}>{source}</option>
            {/each}
          </select>
          <input
            class="flex-1 bg-muma-spotify-light border-none rounded px-3 py-2 text-sm text-white"
            placeholder="id bij die bron"
            bind:value={newExternalId}
          />
          <button
            class="bg-brand text-black font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
            disabled={!newExternalId.trim() || busy}
            onclick={() => {
              const external_id = newExternalId.trim();
              newExternalId = '';
              act(() => setArtistExternalId(name, { source: newSource, external_id, verified: true }), 'Id opgeslagen.');
            }}
          >
            Opslaan
          </button>
        </div>
      {/if}
    </section>

    <ChipEditor
      title="Aliassen"
      hint="Andere schrijfwijzen waaronder deze artiest voorkomt, bijvoorbeeld 'DJ Angerfist'."
      placeholder="Alias"
      items={artist.aliases}
      disabled={!artist.in_library}
      validate={(candidate) => {
        if (candidate.toLowerCase() === artist.name.toLowerCase()) return 'Een artiest is geen alias van zichzelf.';
        if (artist.aliases.some((alias) => alias.toLowerCase() === candidate.toLowerCase())) return 'Die alias staat er al.';
        return null;
      }}
      onadd={(alias) => act(() => addArtistAlias(name, alias), 'Alias toegevoegd.')}
      onremove={(alias) => act(() => removeArtistAlias(name, alias), 'Alias verwijderd.')}
    />

    <GenreRuleEditor
      rules={artist.genre_rules}
      {whiteGenres}
      affected={artist.track_count}
      {busy}
      onadd={(genreId) => act(() => addArtistGenre(name, genreId), 'Regel opgeslagen.')}
      onremove={(genreId) => act(() => removeArtistGenre(name, genreId), 'Regel verwijderd.')}
      onretag={() =>
        act(() => retag('artist', name), (result) => `${result.files} bestanden staan in de wachtrij om opnieuw getagd te worden.`)}
    />
  </CurationShell>
{:else}
  <div class="p-10 text-muma-spotify-text">
    {#if error}{error}{:else}Laden…{/if}
  </div>
{/if}
