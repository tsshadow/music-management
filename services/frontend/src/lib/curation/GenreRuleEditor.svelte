<script>
  /**
   * The genre rules for one artist or one label, and the button that applies them.
   *
   * Saving a rule and retagging the files it matches are deliberately two actions. A
   * rule is cheap to write and cheap to undo; a retag of a few hundred files is
   * neither, and a typo caught before the second click costs nothing. So the count is
   * shown first and the retag waits for a separate press.
   */
  import { Plus, X, Play } from '@lucide/svelte';

  import { t } from '../i18n/index.js';
  import { affectedLabel } from './curation.js';

  let {
    rules = [],
    whiteGenres = [],
    affected = 0,
    busy = false,
    onadd,
    onremove,
    onretag
  } = $props();

  let selected = $state('');

  const available = $derived(
    whiteGenres.filter((genre) => !rules.some((rule) => String(rule.genre_id) === String(genre.id)))
  );
</script>

<section>
  <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">{$t('curation.genreRules')}</h2>
  <p class="text-xs text-muma-spotify-text mt-1 mb-0">
    {$t('curation.genreRulesHelp')}
  </p>

  <div class="flex flex-wrap gap-2 mt-3">
    {#each rules as rule (rule.genre_id)}
      <span class="flex items-center gap-2 bg-muma-spotify-light rounded-full pl-3 pr-2 py-1 text-sm">
        {rule.name}
        {#if rule.created_by}
          <span class="text-[11px] text-muma-spotify-text">{$t('curation.ruleBy', { name: rule.created_by })}</span>
        {/if}
        <button
          class="bg-transparent border-none p-0 cursor-pointer text-muma-spotify-text hover:text-white flex"
          aria-label={$t('curation.ruleRemove', { name: rule.name })}
          onclick={() => onremove?.(rule.genre_id)}
        >
          <X size={14} />
        </button>
      </span>
    {:else}
      <span class="text-sm text-muma-spotify-text">{$t('management.genres.ruleNone')}</span>
    {/each}
  </div>

  <div class="flex gap-2 mt-3">
    <select
      class="flex-1 bg-muma-spotify-light border-none rounded px-3 py-2 text-sm text-white"
      bind:value={selected}
      aria-label={$t('curation.pickGenre')}
    >
      <option value="">{$t('curation.pickApprovedGenre')}</option>
      {#each available as genre (genre.id)}
        <option value={String(genre.id)}>{genre.name}</option>
      {/each}
    </select>
    <button
      class="flex items-center gap-1 bg-brand text-black font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
      disabled={!selected || busy}
      onclick={() => { onadd?.(Number(selected)); selected = ''; }}
    >
      <Plus size={16} /> {$t('management.genres.ruleAdd')}
    </button>
  </div>

  <div class="flex items-center gap-3 mt-4 flex-wrap">
    <span class="text-sm text-muma-spotify-text">{$t('curation.affects', { tracks: affectedLabel(affected) })}</span>
    <button
      class="flex items-center gap-2 bg-muma-spotify-light hover:bg-muma-spotify-highlight text-white font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
      disabled={!affected || busy}
      onclick={() => onretag?.()}
    >
      <Play size={16} /> {$t('curation.applyNow')}
    </button>
  </div>
</section>
