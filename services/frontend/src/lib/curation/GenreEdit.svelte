<script>
  /**
   * Editing one genre: where it sits in the hierarchy. 'Industrial Hardcore' rolls up
   * into 'Hardcore', so a search for Hardcore finds it.
   *
   * Only an accepted genre has anything to edit here. Whether a genre exists at all is
   * curation's question, answered in Beheer; this page answers what else is true about
   * one curation has already accepted. A rejected genre is not part of the library, so
   * it gets an explanation instead of a form.
   */
  import { onMount } from 'svelte';

  import ChipEditor from './ChipEditor.svelte';
  import CurationShell from './CurationShell.svelte';
  import { addParent, canEditGenre, isHardness, parentIsAllowed, parseHardness, removeParent } from './curation.js';
  import { loadGenre, setGenreHardness, setGenreParents } from './curationApi.js';

  let { name, onback } = $props();

  let genre = $state(null);
  let error = $state(null);
  let message = $state(null);
  let busy = $state(false);
  let hardnessInput = $state('');
  let hardnessError = $state(null);

  const editable = $derived(canEditGenre(genre));

  async function refresh() {
    genre = await loadGenre(name);
    hardnessInput = genre.hardness ?? '';
  }

  async function saveParents(parents) {
    error = null;
    message = null;
    busy = true;
    try {
      await setGenreParents(name, parents);
      await refresh();
      message = 'Hiërarchie opgeslagen.';
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }

  async function saveHardness() {
    if (!isHardness(hardnessInput)) {
      hardnessError = 'Moet een geheel getal tussen 0 en 100 zijn, of leeg.';
      return;
    }
    hardnessError = null;
    error = null;
    message = null;
    busy = true;
    try {
      await setGenreHardness(name, parseHardness(hardnessInput));
      await refresh();
      message = 'Hardheid opgeslagen.';
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }

  onMount(async () => {
    try {
      await refresh();
    } catch (e) {
      error = e.message;
    }
  });
</script>

{#if genre}
  <CurationShell
    title={genre.name}
    subtitle={editable
      ? `${genre.occurrences ?? 0} keer gezien in de bibliotheek`
      : 'Dit genre is niet goedgekeurd door de curatie'}
    {error}
    {message}
    {onback}
  >
    {#if editable}
      <ChipEditor
        title="Valt onder"
        hint="Bredere genres waar dit genre bij hoort. De tagger voegt ze toe aan elke track met dit genre."
        placeholder="Bijvoorbeeld Hardcore"
        items={genre.parents}
        {busy}
        validate={(candidate) =>
          parentIsAllowed(genre.name, candidate, genre.parents)
            ? null
            : 'Dat kan niet: een genre valt niet onder zichzelf, en staat er maar één keer in.'}
        onadd={(parent) => saveParents(addParent(genre.parents, parent))}
        onremove={(parent) => saveParents(removeParent(genre.parents, parent))}
      />

      <section>
        <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">Hardheid</h2>
        <p class="text-xs text-muma-spotify-text mt-1 mb-0">
          0 (zacht) tot 100 (hard). Bepaalt in welke van de zachte, middelste of harde
          daily mix dit genre terechtkomt. Leeg laten geeft het genre terug aan de
          automatische schatting.
        </p>
        <div class="flex items-center gap-2 mt-3">
          <input
            type="number"
            min="0"
            max="100"
            step="1"
            aria-label="Hardheid"
            class="w-24 rounded bg-muma-spotify-light px-3 py-1 text-sm"
            bind:value={hardnessInput}
            disabled={busy}
          />
          <button
            type="button"
            class="text-sm rounded bg-muma-spotify-light px-3 py-1 hover:bg-opacity-80 disabled:opacity-50"
            disabled={busy}
            onclick={saveHardness}
          >
            Opslaan
          </button>
        </div>
        {#if hardnessError}
          <p class="text-xs text-red-400 mt-2 mb-0">{hardnessError}</p>
        {/if}
      </section>

      <section>
        <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">Subgenres</h2>
        <p class="text-xs text-muma-spotify-text mt-1 mb-0">
          Genres die onder dit genre vallen. Te wijzigen op hun eigen pagina.
        </p>
        <div class="flex flex-wrap gap-2 mt-3">
          {#each genre.children as child (child)}
            <span class="bg-muma-spotify-light rounded-full px-3 py-1 text-sm">{child}</span>
          {:else}
            <span class="text-sm text-muma-spotify-text">Geen subgenres.</span>
          {/each}
        </div>
      </section>
    {:else}
      <section class="text-sm text-muma-spotify-text">
        <p class="m-0">
          De curatie bepaalt of een genre bestaat; deze pagina bewerkt een genre dat al
          is goedgekeurd. Dit genre staat op <strong>{genre.state}</strong>, dus er is
          niets om in te stellen — de tagger schrijft het nergens weg.
        </p>
        <p class="mt-3 mb-0">Beoordeel het eerst onder Beheer → Genre-curatie.</p>
      </section>
    {/if}
  </CurationShell>
{:else}
  <div class="p-10 text-muma-spotify-text">
    {#if error}{error}{:else}Laden…{/if}
  </div>
{/if}
