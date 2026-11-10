<script>
  /**
   * Editing one label: identity, the parent label, catalogue prefixes, catalogue
   * coverage, the channels linked to it (with unlink, issue #126) and genre rules.
   *
   * The parent label is stored and shown but nothing in the tagger reads it yet. That
   * is on purpose: the relations have to be enterable before a rule that lets a
   * sublabel inherit its parent's genres can be worth writing.
   */
  import { onMount } from 'svelte';

  import { t } from '../i18n/index.js';
  import ChipEditor from './ChipEditor.svelte';
  import CurationShell from './CurationShell.svelte';
  import GenreRuleEditor from './GenreRuleEditor.svelte';
  import LabelCatalog from './LabelCatalog.svelte';
  import LabelChannels from '../LabelChannels.svelte';
  import { isMbid, mbidUrl } from './curation.js';
  import {
    addLabelCatid,
    addLabelGenre,
    loadLabel,
    loadWhiteGenres,
    marked,
    removeLabelCatid,
    removeLabelGenre,
    retag,
    setLabelMbid,
    setLabelParent
  } from './curationApi.js';

  /**
   * @property {string} name - The label's name, from the route.
   * @property {() => void} onback - Back to the label page.
   * @property {(view: string) => void} [onnavigate] - Opens a view (a channel's track list).
   * @property {() => void} [onmanage] - Opens Management > Downloaders > Links.
   */
  let { name, onback, onnavigate, onmanage } = $props();

  let label = $state(null);
  let whiteGenres = $state([]);
  let error = $state(null);
  let message = $state(null);
  let busy = $state(false);
  let mbidDraft = $state('');
  let parentDraft = $state('');

  const mbidValid = $derived(isMbid(mbidDraft));
  const mbidLink = $derived(mbidUrl('label', label?.mbid));

  async function refresh() {
    label = await loadLabel(name);
    mbidDraft = label.mbid || '';
    parentDraft = label.parent_label_id ? String(label.parent_label_id) : '';
  }

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

  onMount(async () => {
    try {
      const [, genres] = await Promise.all([refresh(), loadWhiteGenres()]);
      whiteGenres = genres;
    } catch (e) {
      error = e.message;
    }
  });
</script>

{#if label}
  <CurationShell
    title={label.name}
    subtitle={label.in_library
      ? $t('curation.inLibrary', { count: label.track_count })
      : $t('curation.notInLibrary')}
    {error}
    {message}
    {onback}
  >
    <section>
      <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">MusicBrainz</h2>
      <div class="flex gap-2 mt-3">
        <input
          class="flex-1 bg-muma-spotify-light border-none rounded px-3 py-2 text-sm text-white font-mono"
          placeholder="00000000-0000-0000-0000-000000000000"
          bind:value={mbidDraft}
          disabled={!label.in_library}
        />
        <button
          class="bg-brand text-black font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
          disabled={!mbidValid || busy || !label.in_library}
          onclick={() => act(() => setLabelMbid(name, mbidDraft.trim() || null), $t('curation.mbidSaved'))}
        >
          {$t('common.save')}
        </button>
      </div>
      {#if !mbidValid}
        <p class="text-xs text-red-400 mt-2 mb-0">{$t('curation.mbidInvalidShort')}</p>
      {/if}
      {#if mbidLink}
        <a class="text-xs text-brand mt-2 inline-block" href={mbidLink} target="_blank" rel="noreferrer">
          {$t('curation.openOnMusicBrainz')}
        </a>
      {/if}
    </section>

    <section>
      <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">{$t('curation.parentLabel')}</h2>
      <p class="text-xs text-muma-spotify-text mt-1 mb-0">
        {$t('curation.parentLabelHelp')}
      </p>
      <div class="flex gap-2 mt-3 items-center">
        <input
          class="flex-1 bg-muma-spotify-light border-none rounded px-3 py-2 text-sm text-white"
          placeholder={$t('curation.parentPlaceholder')}
          bind:value={parentDraft}
          disabled={!label.in_library}
        />
        <button
          class="bg-brand text-black font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
          disabled={busy || !label.in_library}
          onclick={() => act(
            () => setLabelParent(name, parentDraft.trim() ? Number(parentDraft.trim()) : null),
            $t('curation.parentSaved'))}
        >
          {$t('common.save')}
        </button>
      </div>
      {#if label.parent_label_name}
        <p class="text-xs text-muma-spotify-text mt-2 mb-0">{$t('curation.parentNow', { name: label.parent_label_name })}</p>
      {/if}
    </section>

    <ChipEditor
      title={$t('curation.catidPrefixes')}
      hint={$t('curation.catidHint')}
      placeholder={$t('curation.catidPlaceholder')}
      items={label.catids}
      disabled={!label.in_library}
      validate={(candidate) =>
        label.catids.some((catid) => catid.toUpperCase() === candidate.toUpperCase())
          ? $t('curation.catidExists')
          : null}
      onadd={(catid) => act(() => addLabelCatid(name, catid), $t('curation.prefixAdded'))}
      onremove={(catid) => act(() => removeLabelCatid(name, catid), $t('curation.prefixRemoved'))}
    />

    {#if label.in_library}
      <LabelCatalog name={label.name} />
    {/if}

    <LabelChannels
      kind="label"
      name={label.name}
      {onnavigate}
      {onmanage}
      canManage
      canUnlink
      onmessage={(text) => { error = null; message = text; }}
      onerror={(text) => { message = null; error = text; }}
    />

    <GenreRuleEditor
      rules={label.genre_rules}
      {whiteGenres}
      affected={label.track_count}
      {busy}
      onadd={(genreId) =>
        act(() => addLabelGenre(name, genreId), (result) => marked(result, $t('curation.ruleSaved')))}
      onremove={(genreId) =>
        act(() => removeLabelGenre(name, genreId), (result) => marked(result, $t('curation.ruleRemoved')))}
      onretag={() =>
        act(() => retag('label', name), (result) => $t('curation.retagQueued', { count: result.files }))}
    />
  </CurationShell>
{:else}
  <div class="p-10 text-muma-spotify-text">
    {#if error}{error}{:else}{$t('common.loading')}{/if}
  </div>
{/if}
