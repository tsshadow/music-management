<script>
  /**
   * Editing one genre: where it sits in the hierarchy. 'Industrial Hardcore' rolls up
   * into 'Hardcore', so a search for Hardcore finds it.
   *
   * Only an accepted genre has anything to edit here. Whether a genre exists at all is
   * curation's question, answered in Management; this page answers what else is true about
   * one curation has already accepted. A rejected genre is not part of the library, so
   * it gets an explanation instead of a form.
   */
  import { onMount } from 'svelte';

  import { t } from '../i18n/index.js';
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
      message = $t('curation.hierarchySaved');
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
  }

  async function saveHardness() {
    if (!isHardness(hardnessInput)) {
      hardnessError = $t('curation.hardnessInvalid');
      return;
    }
    hardnessError = null;
    error = null;
    message = null;
    busy = true;
    try {
      await setGenreHardness(name, parseHardness(hardnessInput));
      await refresh();
      message = $t('curation.hardnessSaved');
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
      ? $t('curation.genreSeen', { count: genre.occurrences ?? 0 })
      : $t('curation.genreNotApproved')}
    {error}
    {message}
    {onback}
  >
    {#if editable}
      <ChipEditor
        title={$t('curation.parentsTitle')}
        hint={$t('curation.parentsHint')}
        placeholder={$t('curation.parentsPlaceholder')}
        items={genre.parents}
        {busy}
        validate={(candidate) =>
          parentIsAllowed(genre.name, candidate, genre.parents, genre.descendants ?? [])
            ? null
            : $t('curation.parentNotAllowed')}
        onadd={(parent) => saveParents(addParent(genre.parents, parent))}
        onremove={(parent) => saveParents(removeParent(genre.parents, parent))}
      />

      <section>
        <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">{$t('management.genres.hardness')}</h2>
        <p class="text-xs text-muma-spotify-text mt-1 mb-0">
          {$t('curation.hardnessHelp')}
        </p>
        <div class="flex items-center gap-2 mt-3">
          <input
            type="number"
            min="0"
            max="100"
            step="1"
            aria-label={$t('management.genres.hardness')}
            class="w-24 rounded bg-muma-spotify-light px-3 py-1 text-sm"
            bind:value={hardnessInput}
            disabled={busy}
          />
          <button
            type="button"
            class="text-sm rounded bg-muma-spotify-light px-3 py-1 hover:bg-muma-spotify-light/80 disabled:opacity-50"
            disabled={busy}
            onclick={saveHardness}
          >
            {$t('common.save')}
          </button>
        </div>
        {#if hardnessError}
          <p class="text-xs text-red-400 mt-2 mb-0">{hardnessError}</p>
        {/if}
      </section>

      <section>
        <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">{$t('curation.subgenres')}</h2>
        <p class="text-xs text-muma-spotify-text mt-1 mb-0">
          {$t('curation.subgenresHelp')}
        </p>
        <div class="flex flex-wrap gap-2 mt-3">
          {#each genre.children as child (child)}
            <span class="bg-muma-spotify-light rounded-full px-3 py-1 text-sm">{child}</span>
          {:else}
            <span class="text-sm text-muma-spotify-text">{$t('curation.noSubgenres')}</span>
          {/each}
        </div>
      </section>
    {:else}
      <section class="text-sm text-muma-spotify-text">
        <p class="m-0">
          {$t('curation.genreNotEditableBefore')} <strong>{genre.state}</strong>{$t('curation.genreNotEditableAfter')}
        </p>
        <p class="mt-3 mb-0">{$t('curation.reviewFirst')}</p>
      </section>
    {/if}
  </CurationShell>
{:else}
  <div class="p-10 text-muma-spotify-text">
    {#if error}{error}{:else}{$t('common.loading')}{/if}
  </div>
{/if}
