<script>
  import { untrack } from 'svelte';
  import { t } from './i18n/index.js';
  import { authParams, mumaUser, viewMode } from './store.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import {
    DEFAULT_PRESET_SIZE,
    PRESET_SORTS,
    createPreset,
    normalizePreset,
    presetParams,
    presetQuery,
    refreshPresets,
    updatePreset,
  } from './presets.js';
  import { notify } from './notifications.js';
  import { FORM_LABEL_KEYS, SET_FORMS } from './trackForm.js';
  import MultiPicker from './MultiPicker.svelte';
  import TrackList from './TrackList.svelte';

  /**
   * Advanced search, and the way to keep what it finds: every cluster LMS can filter on --
   * genres, artists, labels, festivals, years -- as lists that are OR'd within a kind and AND'd
   * across kinds, plus a rating range, a sort, songs-or-sets and -- for sets -- the Soort (track
   * form: sets & mixes, live sets, podcasts), which Android Auto also plays the preset with. The list underneath answers
   * as the query changes, and "Opslaan als snelkoppeling" makes the query one of the user's
   * presets: a tile on the home grid, and a row in Android Auto's Afspeellijsten on the next
   * browse, since the car reads the same list from the server.
   *
   * Opened with a `preset` it edits that one instead: same form, pre-filled, saving overwrites.
   */
  const { preset = null, onnavigate } = $props();

  const PREVIEW_COUNT = 50;

  // The form is seeded from the preset once; Dashboard keys this component on the preset id, so
  // opening another one mounts a fresh form rather than re-seeding this one.
  const initial = untrack(() => preset);

  let name = $state(initial?.name ?? '');
  let genres = $state([...(initial?.genres ?? [])]);
  let artists = $state([...(initial?.artists ?? [])]);
  let labels = $state([...(initial?.labels ?? [])]);
  let festivals = $state([...(initial?.festivals ?? [])]);
  let years = $state([...(initial?.years ?? [])]);
  let sort = $state(initial?.sort ?? 'recent');
  let minRating = $state(initial?.minRating ?? 0);
  let maxRating = $state(initial?.maxRating ?? 5);
  let mode = $state(initial ? (initial.length === 'long' ? 'sets' : 'songs') : untrack(() => $viewMode));
  let size = $state(initial?.size ?? DEFAULT_PRESET_SIZE);
  // Only offered, and only saved, in sets mode: presetParams drops it for songs.
  let form = $state(initial?.form ?? '');

  let genreOptions = $state([]);
  let labelOptions = $state([]);
  let festivalOptions = $state([]);
  let yearOptions = $state([]);

  let tracks = $state([]);
  let previewLoading = $state(false);
  let saving = $state(false);
  let previewSeq = 0;

  /** The query as {@link presetQuery} wants it; `normalizePreset` gives it the same shape a saved one has. */
  const draft = $derived(
    normalizePreset({
      id: preset?.id ?? '',
      name,
      params: presetParams({ genres, artists, labels, festivals, years, sort, minRating, maxRating, form, viewMode: mode, size }),
    }),
  );

  const hasFilter = $derived(
    genres.length + artists.length + labels.length + festivals.length + years.length > 0 ||
      minRating > 0 ||
      maxRating < 5 ||
      (mode === 'sets' && Boolean(form)),
  );

  const ratingSteps = [0, 1, 2, 3, 4, 5];

  $effect(() => {
    if (!$authParams) return;
    loadOptions();
  });

  async function loadOptions() {
    const value = (row) => row?.value ?? row?.name ?? '';
    // Each list on its own: a server that refuses one of them (subsonicJson throws on a failed
    // answer) leaves that picker empty rather than all four.
    const rowsOf = (method, path, params) =>
      subsonicJson(method, params)
        .then((body) => listOf(body, path))
        .catch((error) => {
          console.warn('Could not load a cluster list', method, error);
          return [];
        });
    try {
      const [genreRows, labelRows, yearRows, festivalRows] = await Promise.all([
        rowsOf('getGenres', 'genres.genre'),
        rowsOf('getRecordLabels', 'recordLabels.recordLabel'),
        rowsOf('getYears', 'years.year'),
        rowsOf('getTags', 'tags.tag', { name: 'FESTIVAL' }),
      ]);
      genreOptions = genreRows.map(value).filter(Boolean).sort((a, b) => a.localeCompare(b));
      labelOptions = labelRows.map(value).filter(Boolean).sort((a, b) => a.localeCompare(b));
      yearOptions = yearRows.map(value).filter(Boolean).sort((a, b) => b.localeCompare(a));
      festivalOptions = festivalRows.map(value).filter(Boolean).sort((a, b) => a.localeCompare(b));
    } catch (error) {
      console.error('Could not load the cluster lists', error);
    }
  }

  /** Artists are too many for one list; ask LMS as the listener types. */
  async function searchArtists(query) {
    const body = await subsonicJson('getArtistList', { type: 'alphabetical', size: 12, query });
    return listOf(body, 'artistList.artist').map((row) => row?.name ?? '').filter(Boolean);
  }

  // The preview follows the query, a beat behind the last change so a chip row being typed into
  // does not fire a request per keystroke. A later query cancels an earlier answer.
  $effect(() => {
    const target = draft;
    const auth = $authParams;
    if (!auth) return;
    const seq = ++previewSeq;
    previewLoading = true;
    const handle = setTimeout(async () => {
      try {
        const { method, params } = presetQuery(target, { viewMode: mode, count: PREVIEW_COUNT });
        const page = listOf(await subsonicJson(method, params), 'songs.song');
        if (seq === previewSeq) tracks = page;
      } catch (error) {
        console.error('Preview failed', error);
        if (seq === previewSeq) tracks = [];
      } finally {
        if (seq === previewSeq) previewLoading = false;
      }
    }, 300);
    return () => clearTimeout(handle);
  });

  /** "Random Uptempo Hardcore", "Recent Angerfist (2024)": the sort word first, as the old tiles were named. */
  function defaultName() {
    const sortWord = sort === 'random' ? $t('presets.randomWord') : $t('presets.recentWord');
    const subject = [...artists, ...festivals, ...labels, ...genres].slice(0, 2).join(', ') || $t('presets.everything');
    const year = years.length ? ` (${years.join(', ')})` : '';
    return `${sortWord} ${subject}${year}`;
  }

  async function save() {
    const userId = $mumaUser?.id;
    if (!userId || saving) return;
    const finalName = name.trim() || defaultName();
    const params = presetParams({ genres, artists, labels, festivals, years, sort, minRating, maxRating, form, viewMode: mode, size });
    saving = true;
    try {
      let id = preset?.id;
      if (preset) {
        await updatePreset(userId, preset.id, { name: finalName, params });
      } else {
        ({ id } = await createPreset(userId, { name: finalName, params }));
      }
      await refreshPresets(userId);
      notify.success($t('presets.saved'));
      onnavigate?.(id ? `preset:${id}` : 'home');
    } catch (error) {
      console.error(error);
      notify.error($t('presets.saveFailed'));
    } finally {
      saving = false;
    }
  }
</script>

<div class="flex flex-col gap-8 pb-12">
  <header>
    <div class="text-xs font-bold uppercase tracking-wider mb-2 text-muma-spotify-text">
      {preset ? $t('presetBuilder.editKicker') : $t('presetBuilder.kicker')}
    </div>
    <h1 class="text-3xl md:text-5xl font-black mb-3 break-words">
      {preset ? preset.name : $t('presetBuilder.title')}
    </h1>
    <p class="text-sm text-muma-spotify-text max-w-2xl m-0">{$t('presetBuilder.intro')}</p>
  </header>

  <form class="grid gap-6 md:grid-cols-2" onsubmit={(event) => { event.preventDefault(); save(); }}>
    <div class="md:col-span-2 flex flex-wrap gap-2" role="radiogroup" aria-label={$t('presetBuilder.mode')}>
      {#each ['songs', 'sets'] as option (option)}
        <button
          type="button"
          role="radio"
          aria-checked={mode === option}
          class="px-4 py-1.5 rounded-full text-sm font-bold border-none cursor-pointer transition-colors {mode === option ? 'bg-white text-black' : 'bg-muma-spotify-light text-white hover:bg-muma-spotify-hover'}"
          onclick={() => (mode = option)}
        >{$t(option === 'songs' ? 'nav.songs' : 'nav.sets')}</button>
      {/each}
    </div>

    <MultiPicker id="pb-genres" label={$t('presetBuilder.genres')} selected={genres} options={genreOptions} placeholder={$t('presetBuilder.addPlaceholder')} onchange={(v) => (genres = v)} />
    <MultiPicker id="pb-artists" label={$t('presetBuilder.artists')} selected={artists} onsearch={searchArtists} placeholder={$t('presetBuilder.addPlaceholder')} onchange={(v) => (artists = v)} />
    <MultiPicker id="pb-labels" label={$t('presetBuilder.labels')} selected={labels} options={labelOptions} placeholder={$t('presetBuilder.addPlaceholder')} onchange={(v) => (labels = v)} />
    <MultiPicker id="pb-festivals" label={$t('presetBuilder.festivals')} selected={festivals} options={festivalOptions} placeholder={$t('presetBuilder.addPlaceholder')} onchange={(v) => (festivals = v)} />
    <MultiPicker id="pb-years" label={$t('presetBuilder.years')} selected={years} options={yearOptions} placeholder={$t('presetBuilder.addPlaceholder')} onchange={(v) => (years = v)} />

    <div class="flex flex-col gap-2">
      <label for="pb-sort" class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('presetBuilder.sort')}</label>
      <select id="pb-sort" class="bg-muma-spotify-light text-white border-none px-3 py-2 rounded-md text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={sort}>
        {#each PRESET_SORTS as option (option.id)}
          <option value={option.id}>{$t(option.labelKey)}</option>
        {/each}
      </select>
    </div>

    {#if mode === 'sets'}
      <div class="flex flex-col gap-2">
        <label for="pb-form" class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('filter.form.label')}</label>
        <select id="pb-form" class="bg-muma-spotify-light text-white border-none px-3 py-2 rounded-md text-sm cursor-pointer focus:outline focus:outline-1 focus:outline-brand" bind:value={form}>
          <option value="">{$t('filter.form.any')}</option>
          {#each SET_FORMS as option (option)}
            <option value={option}>{$t(FORM_LABEL_KEYS[option])}</option>
          {/each}
        </select>
      </div>
    {/if}

    <div class="flex flex-col gap-2">
      <span class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('presetBuilder.rating')}</span>
      <div class="flex items-center gap-2 flex-wrap">
        <label class="flex items-center gap-2 text-sm">
          <span>{$t('presetBuilder.ratingMin')}</span>
          <select class="bg-muma-spotify-light text-white border-none px-3 py-2 rounded-md text-sm cursor-pointer" bind:value={minRating} onchange={() => { if (maxRating < minRating) maxRating = minRating; }}>
            {#each ratingSteps as step (step)}
              <option value={step}>{step === 0 ? $t('filter.allRatings') : `${step}★`}</option>
            {/each}
          </select>
        </label>
        <label class="flex items-center gap-2 text-sm">
          <span>{$t('presetBuilder.ratingMax')}</span>
          <select class="bg-muma-spotify-light text-white border-none px-3 py-2 rounded-md text-sm cursor-pointer" bind:value={maxRating} onchange={() => { if (minRating > maxRating) minRating = maxRating; }}>
            {#each ratingSteps as step (step)}
              <option value={step}>{`${step}★`}</option>
            {/each}
          </select>
        </label>
      </div>
    </div>

    <div class="flex flex-col gap-2">
      <label for="pb-size" class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('presetBuilder.size')}</label>
      <input id="pb-size" type="number" min="1" max="5000" class="bg-muma-spotify-light text-white border-none px-3 py-2 rounded-md text-sm w-32" bind:value={size} />
    </div>

    <div class="flex flex-col gap-2">
      <label for="pb-name" class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('presetBuilder.name')}</label>
      <input id="pb-name" type="text" class="bg-muma-spotify-light text-white border-none px-3 py-2 rounded-md text-sm placeholder:text-[#777]" placeholder={defaultName()} bind:value={name} />
    </div>

    <div class="md:col-span-2 flex items-center gap-4 flex-wrap">
      <button
        type="submit"
        class="bg-brand text-black font-bold py-2 px-6 rounded-full border-none cursor-pointer hover:scale-105 active:scale-95 transition disabled:opacity-50 disabled:hover:scale-100"
        disabled={saving || !$mumaUser?.id}
      >{preset ? $t('presetBuilder.saveChanges') : $t('presetBuilder.save')}</button>
      {#if !$mumaUser?.id}
        <span class="text-sm text-muma-spotify-text">{$t('presetBuilder.signInToSave')}</span>
      {/if}
      {#if !hasFilter}
        <span class="text-sm text-muma-spotify-text">{$t('presetBuilder.noFilterHint')}</span>
      {/if}
    </div>
  </form>

  <section class="flex flex-col gap-4" aria-live="polite">
    <h2 class="text-xl font-bold m-0">
      {$t('presetBuilder.preview')}
      {#if tracks.length > 0}
        <span class="text-muma-spotify-text text-sm font-medium">· {$t('presetBuilder.previewCount', { count: tracks.length })}</span>
      {/if}
    </h2>
    {#if previewLoading && tracks.length === 0}
      <div class="text-muma-spotify-text p-12 text-center">{$t('common.loading')}</div>
    {:else if tracks.length === 0}
      <div class="text-muma-spotify-text p-12 text-center">{$t('presets.empty')}</div>
    {:else}
      <TrackList {tracks} onnavigate={onnavigate} />
    {/if}
  </section>
</div>
