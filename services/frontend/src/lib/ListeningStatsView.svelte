<script>
  /**
   * What you listened to, as opposed to what is in the library.
   *
   * The page leads with the caveat rather than burying it. Most of the recorded
   * history is not linked to a library track, and only a fraction of it ever
   * recorded how long it played, so the totals and the rankings are counting
   * different populations. Both facts sit above the charts, in the same type as
   * the numbers they qualify -- a footnote would let a reader take the top-ten
   * lists for the whole story, which is the one mistake this page can cause.
   *
   * Charts are bars made of divs, like AnalyticsPanel: a listening page is not
   * worth a charting dependency, and every value is in the DOM as text as well,
   * so hovering is not the only way to read it.
   *
   * Genre and release year filter every panel at once. The filter lives in the
   * URL's query string (`?genre=Hardstyle&year_from=2015`), replaced in place on
   * every change, so a filtered view can be bookmarked or shared and the path the
   * app router owns stays `/listening`. A bar in the genre or year chart is itself
   * the button that toggles its filter; the filter bar above only makes the same
   * state editable and visible. Because a filter can only test a track, it drops
   * every unmatched listen, and the page says how many right under the filter.
   */
  import { onMount } from 'svelte';
  import {
    CalendarRange,
    Clock,
    Headphones,
    ListMusic,
    Radio,
    Shapes,
    Tag,
    TriangleAlert,
    Users,
    X,
  } from '@lucide/svelte';

  import MultiPicker from './MultiPicker.svelte';
  import { t, format } from './i18n/index.js';
  import {
    DEFAULT_PERIOD,
    NO_FILTERS,
    PERIODS,
    UNKNOWN_YEAR,
    bucketLabel,
    byDecade,
    filtersFromSearch,
    filtersToSearch,
    hasFilters,
    loadGenreOptions,
    loadListening,
    measuredPercent,
    peak,
    setYearBound,
    splitDuration,
    toggleDecade,
    toggleGenre,
    toggleYear,
    unmatchedPercent,
    yearSelected,
  } from './listeningStats.js';

  const { onnavigate } = $props();

  let period = $state(DEFAULT_PERIOD);
  let filters = $state({ ...NO_FILTERS });
  let genreOptions = $state([]);
  let yearView = $state('year');
  let data = $state(null);
  let isLoading = $state(true);
  let loadSeq = 0;

  const summary = $derived(data?.summary ?? null);
  const buckets = $derived(data?.timeline?.buckets ?? []);
  const hours = $derived(data?.clock?.hours ?? []);
  const weekdays = $derived(data?.clock?.weekdays ?? []);
  const sources = $derived(data?.sources?.sources ?? []);
  const topTracks = $derived(data?.tracks?.tracks ?? []);
  const topArtists = $derived(data?.artists?.artists ?? []);
  const topLabels = $derived(data?.labels?.labels ?? []);
  const topGenres = $derived(data?.genres?.genres ?? []);
  const years = $derived(data?.years?.years ?? []);
  const unknownYear = $derived(data?.years?.unknown ?? { listens: 0, tracks: 0 });
  const decades = $derived(byDecade(years));
  const filtered = $derived(hasFilters(filters));
  // Any panel will do: each filtered response carries the same count.
  const excludedUnmatched = $derived(
    data?.summary?.excluded_unmatched ??
      data?.genres?.excluded_unmatched ??
      data?.years?.excluded_unmatched ??
      0,
  );

  const unmatched = $derived(unmatchedPercent(summary));
  const measured = $derived(measuredPercent(summary));
  const listened = $derived(splitDuration(summary?.estimated_secs));

  const num = (value) => $format.number(value);

  /**
   * Fetch every panel for the current period and filter.
   *
   * Only the first load blanks the page; later ones keep the old numbers on
   * screen until the new ones arrive, so toggling a filter does not flash the
   * whole page. A response that arrives after a newer request was sent is dropped.
   */
  async function load() {
    const seq = ++loadSeq;
    const result = await loadListening(period, filters);
    if (seq !== loadSeq) return;
    data = result;
    isLoading = false;
  }

  /** Put the period and filter in the address bar without adding a history entry. */
  function writeUrl() {
    const search = filtersToSearch(period, filters);
    const url = window.location.pathname + (search ? `?${search}` : '');
    if (url !== window.location.pathname + window.location.search) {
      window.history.replaceState(window.history.state, '', url);
    }
  }

  /** Change period and/or filter, reflect it in the URL and reload every panel. */
  function apply(nextPeriod, nextFilters) {
    period = nextPeriod;
    filters = nextFilters;
    writeUrl();
    load();
  }

  onMount(() => {
    const fromUrl = filtersFromSearch(window.location.search);
    period = fromUrl.period;
    filters = fromUrl.filters;
    load();
    loadGenreOptions().then((options) => (genreOptions = options));
  });

  function selectPeriod(id) {
    if (id === period) return;
    apply(id, filters);
  }

  const yearPeak = $derived(peak(years));
  const decadePeak = $derived(peak(decades));
  const genrePeak = $derived(peak(topGenres));
</script>

<div class="p-4 sm:p-6 flex flex-col gap-6">

  <header class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-3xl font-black tracking-tight text-white">{$t('listening.title')}</h1>
      <p class="text-sm text-muma-spotify-text mt-1">{$t('listening.subtitle')}</p>
    </div>
    <div class="flex gap-1 bg-black/40 border border-white/5 rounded-full p-1">
      {#each PERIODS as option (option.id)}
        <button
          class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {period === option.id
            ? 'bg-brand text-black'
            : 'text-muma-spotify-text hover:text-white'}"
          onclick={() => selectPeriod(option.id)}
        >{$t(`listening.period.${option.id}`)}</button>
      {/each}
    </div>
  </header>

  <section class="bg-black/40 p-4 rounded-xl border border-white/5 flex flex-col gap-3" aria-label={$t('listening.filter.title')}>
    <div class="flex flex-col lg:flex-row gap-4">
      <div class="flex-1 min-w-0">
        <MultiPicker
          id="listening-genre"
          label={$t('listening.filter.genre')}
          selected={filters.genres}
          options={genreOptions}
          placeholder={$t('listening.filter.genrePlaceholder')}
          onchange={(genres) => apply(period, { ...filters, genres })}
        />
      </div>
      <div class="flex flex-col gap-2 lg:w-72">
        <label for="listening-year-from" class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('listening.filter.yearRange')}</label>
        <div class="flex items-center gap-2">
          <input
            id="listening-year-from"
            type="number"
            inputmode="numeric"
            min="1900"
            max="2100"
            placeholder={$t('listening.filter.from')}
            aria-label={$t('listening.filter.from')}
            value={filters.yearFrom ?? ''}
            onchange={(event) => apply(period, setYearBound(filters, 'yearFrom', event.currentTarget.value))}
            class="w-full min-w-0 bg-muma-spotify-light text-white text-sm rounded-md px-3 min-h-11 border-none outline-none focus:outline focus:outline-1 focus:outline-brand placeholder:text-[#777]"
          />
          <span class="text-muma-spotify-subtle">–</span>
          <input
            id="listening-year-to"
            type="number"
            inputmode="numeric"
            min="1900"
            max="2100"
            placeholder={$t('listening.filter.to')}
            aria-label={$t('listening.filter.to')}
            value={filters.yearTo ?? ''}
            onchange={(event) => apply(period, setYearBound(filters, 'yearTo', event.currentTarget.value))}
            class="w-full min-w-0 bg-muma-spotify-light text-white text-sm rounded-md px-3 min-h-11 border-none outline-none focus:outline focus:outline-1 focus:outline-brand placeholder:text-[#777]"
          />
        </div>
      </div>
    </div>

    {#if filtered}
      <div class="flex flex-wrap items-center gap-2" data-testid="active-filters">
        {#each filters.years as year (year)}
          <span class="flex items-center gap-1 bg-brand text-black text-xs font-bold rounded-full pl-3 pr-1 py-0.5">
            {year}
            <button
              type="button"
              class="w-5 h-5 rounded-full flex items-center justify-center hover:bg-black/10"
              aria-label={$t('listening.filter.remove', { name: year })}
              onclick={() => apply(period, toggleYear(filters, year))}
            ><X size={12} /></button>
          </span>
        {/each}
        {#if filters.unknownYear}
          <span class="flex items-center gap-1 bg-brand text-black text-xs font-bold rounded-full pl-3 pr-1 py-0.5">
            {$t('listening.unknownYear')}
            <button
              type="button"
              class="w-5 h-5 rounded-full flex items-center justify-center hover:bg-black/10"
              aria-label={$t('listening.filter.remove', { name: $t('listening.unknownYear') })}
              onclick={() => apply(period, toggleYear(filters, UNKNOWN_YEAR))}
            ><X size={12} /></button>
          </span>
        {/if}
        {#if filters.yearFrom !== null || filters.yearTo !== null}
          <span class="flex items-center gap-1 bg-brand text-black text-xs font-bold rounded-full pl-3 pr-1 py-0.5">
            {filters.yearFrom ?? '…'}–{filters.yearTo ?? '…'}
            <button
              type="button"
              class="w-5 h-5 rounded-full flex items-center justify-center hover:bg-black/10"
              aria-label={$t('listening.filter.remove', { name: `${filters.yearFrom ?? '…'}–${filters.yearTo ?? '…'}` })}
              onclick={() => apply(period, { ...filters, yearFrom: null, yearTo: null })}
            ><X size={12} /></button>
          </span>
        {/if}
        <button
          type="button"
          class="bg-transparent border border-muma-spotify-muted text-white text-xs font-bold px-3 py-1 rounded-full hover:border-white"
          onclick={() => apply(period, { ...NO_FILTERS })}
        >{$t('listening.filter.clear')}</button>
      </div>
      {#if excludedUnmatched > 0}
        <p class="text-xs text-[#d0d0d0] flex items-start gap-2" data-testid="excluded-unmatched">
          <TriangleAlert size={14} class="text-yellow-500/80 shrink-0 mt-0.5" />
          {$t('listening.filter.excluded', { count: num(excludedUnmatched) })}
        </p>
      {/if}
    {/if}
  </section>

  {#if isLoading}
    <p class="text-sm text-muma-spotify-subtle">{$t('listening.loading')}</p>
  {:else if !summary}
    <p class="text-sm text-muma-spotify-subtle">{$t('listening.unavailable')}</p>
  {:else if summary.listens === 0}
    <p class="text-sm text-muma-spotify-subtle">{filtered ? $t('listening.emptyFiltered') : $t('listening.empty')}</p>
  {:else}

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-muma-spotify-text flex items-center gap-1.5">
          <Headphones size={13} class="text-brand" /> {$t('listening.tile.listens')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">{num(summary.listens)}</p>
        <p class="text-[11px] text-muma-spotify-subtle mt-1">{$t('listening.tile.matchedOf', { matched: num(summary.matched) })}</p>
      </div>
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-muma-spotify-text flex items-center gap-1.5">
          <ListMusic size={13} class="text-brand" /> {$t('listening.tile.tracks')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">{num(summary.tracks)}</p>
        <p class="text-[11px] text-muma-spotify-subtle mt-1">{$t('listening.tile.matchedOnly')}</p>
      </div>
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-muma-spotify-text flex items-center gap-1.5">
          <Users size={13} class="text-brand" /> {$t('listening.tile.artists')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">{num(summary.artists)}</p>
        <p class="text-[11px] text-muma-spotify-subtle mt-1">{$t('listening.tile.matchedOnly')}</p>
      </div>
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-muma-spotify-text flex items-center gap-1.5">
          <Clock size={13} class="text-brand" /> {$t('listening.tile.time')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">
          {num(listened.hours)}<span class="text-lg">{$t('listening.hoursShort')}</span>
          {listened.minutes}<span class="text-lg">{$t('listening.minutesShort')}</span>
        </p>
        <p class="text-[11px] text-muma-spotify-subtle mt-1">{$t('listening.tile.estimated')}</p>
      </div>
    </div>

    <div class="bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-4 flex items-start gap-3">
      <TriangleAlert size={16} class="text-yellow-500/80 shrink-0 mt-0.5" />
      <div class="text-xs text-[#d0d0d0] leading-relaxed">
        {#if !summary.filtered}
          <p>{$t('listening.caveat.unmatched', { percent: unmatched, count: num(summary.unmatched) })}</p>
        {/if}
        <p class={summary.filtered ? '' : 'mt-1'}>{$t('listening.caveat.measured', { percent: measured, count: num(summary.measured_listens) })}</p>
      </div>
    </div>

    <div class="bg-black/40 p-5 rounded-xl border border-white/5">
      <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-5">{$t('listening.timeline')}</h2>
      {#if buckets.length === 0}
        <p class="text-xs text-muma-spotify-subtle">{$t('listening.empty')}</p>
      {:else}
        <div class="flex items-end gap-0.5 h-40">
          {#each buckets as bar (bar.bucket)}
            <div class="flex-1 min-w-[3px] flex flex-col justify-end h-full group relative">
              <div
                class="bg-white/10 rounded-t-sm"
                style="height: {(bar.unmatched / peak(buckets)) * 100}%"
              ></div>
              <div
                class="bg-brand/70 group-hover:bg-brand transition-colors"
                style="height: {(bar.matched / peak(buckets)) * 100}%"
              ></div>
              <div class="absolute -top-8 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                {bar.bucket}: {num(bar.listens)}
              </div>
            </div>
          {/each}
        </div>
        <div class="flex justify-between mt-2 text-[10px] text-muma-spotify-subtle font-mono tabular-nums">
          <span>{bucketLabel(buckets[0].bucket, data.bucket)}</span>
          <span>{bucketLabel(buckets[buckets.length - 1].bucket, data.bucket)}</span>
        </div>
        <p class="text-[10px] text-muma-spotify-subtle mt-3">{$t('listening.timelineLegend')}</p>
      {/if}
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <div class="bg-black/40 p-5 rounded-xl border border-white/5" data-testid="genre-panel">
        <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-1 flex items-center gap-1.5">
          <Shapes size={13} class="text-brand" /> {$t('listening.topGenres')}
        </h2>
        <p class="text-[10px] text-muma-spotify-subtle mb-4">
          {$t('listening.genresNote', { matched: num(data.genres?.matched ?? 0), untagged: num(data.genres?.untagged ?? 0) })}
        </p>
        {#if topGenres.length === 0}
          <p class="text-xs text-muma-spotify-subtle">{$t('listening.empty')}</p>
        {:else}
          <ul class="flex flex-col gap-1">
            {#each topGenres as row (row.genre_id)}
              {@const active = filters.genres.includes(row.genre)}
              <li>
                <button
                  type="button"
                  class="w-full flex items-center gap-3 text-left rounded-md px-2 py-1.5 min-h-9 transition-colors hover:bg-white/5 {active ? 'bg-white/5' : ''}"
                  aria-pressed={active}
                  title={$t('listening.toggleFilter')}
                  onclick={() => apply(period, toggleGenre(filters, row.genre))}
                >
                  <span class="text-[11px] w-32 sm:w-40 shrink-0 truncate {active ? 'text-white font-bold' : 'text-white'}">{row.genre}</span>
                  <span class="h-2 flex-1 bg-white/5 rounded-full overflow-hidden">
                    <span class="block h-full rounded-full {active ? 'bg-brand' : 'bg-brand/50'}" style="width: {(row.listens / genrePeak) * 100}%"></span>
                  </span>
                  <span class="text-[11px] text-muma-spotify-text tabular-nums w-12 text-right shrink-0">{num(row.listens)}</span>
                </button>
              </li>
            {/each}
          </ul>
          <p class="text-[10px] text-muma-spotify-subtle mt-3">{$t('listening.tapToFilter')}</p>
        {/if}
      </div>

      <div class="bg-black/40 p-5 rounded-xl border border-white/5" data-testid="year-panel">
        <div class="flex items-start justify-between gap-3 mb-1">
          <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text flex items-center gap-1.5">
            <CalendarRange size={13} class="text-brand" /> {$t('listening.releaseYears')}
          </h2>
          <div class="flex gap-1 bg-black/40 border border-white/5 rounded-full p-0.5 shrink-0">
            {#each ['year', 'decade'] as view (view)}
              <button
                type="button"
                class="px-3 py-1 rounded-full text-[10px] font-bold transition-colors {yearView === view
                  ? 'bg-brand text-black'
                  : 'text-muma-spotify-text hover:text-white'}"
                aria-pressed={yearView === view}
                onclick={() => (yearView = view)}
              >{$t(`listening.yearView.${view}`)}</button>
            {/each}
          </div>
        </div>
        <p class="text-[10px] text-muma-spotify-subtle mb-4">{$t('listening.yearsNote')}</p>
        {#if years.length === 0 && unknownYear.listens === 0}
          <p class="text-xs text-muma-spotify-subtle">{$t('listening.empty')}</p>
        {:else}
          {#if yearView === 'year'}
            <div class="flex items-end gap-0.5 h-32">
              {#each years as row (row.year)}
                {@const active = yearSelected(filters, row.year)}
                <button
                  type="button"
                  class="flex-1 min-w-[6px] flex flex-col justify-end h-full group relative"
                  aria-pressed={active}
                  aria-label={$t('listening.yearBar', { year: row.year, count: num(row.listens) })}
                  onclick={() => apply(period, toggleYear(filters, row.year))}
                >
                  <span class="block rounded-t-sm transition-colors {active ? 'bg-brand' : 'bg-brand/50 group-hover:bg-brand/80'}" style="height: {(row.listens / yearPeak) * 100}%"></span>
                  <span class="absolute -top-7 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                    {row.year}: {num(row.listens)}
                  </span>
                </button>
              {/each}
            </div>
            {#if years.length > 0}
              <div class="flex justify-between mt-2 text-[10px] text-muma-spotify-subtle font-mono tabular-nums">
                <span>{years[0].year}</span>
                <span>{years[years.length - 1].year}</span>
              </div>
            {/if}
          {:else}
            <div class="flex items-end gap-2 h-32">
              {#each decades as row (row.decade)}
                {@const active = filters.yearFrom === row.decade && filters.yearTo === row.decade + 9}
                <button
                  type="button"
                  class="flex-1 flex flex-col justify-end h-full group relative"
                  aria-pressed={active}
                  aria-label={$t('listening.decadeBar', { decade: row.decade, count: num(row.listens) })}
                  onclick={() => apply(period, toggleDecade(filters, row.decade))}
                >
                  <span class="block rounded-t-sm transition-colors {active ? 'bg-brand' : 'bg-brand/50 group-hover:bg-brand/80'}" style="height: {(row.listens / decadePeak) * 100}%"></span>
                </button>
              {/each}
            </div>
            <div class="flex gap-2 mt-2 text-[10px] text-muma-spotify-subtle font-mono tabular-nums">
              {#each decades as row (row.decade)}
                <span class="flex-1 text-center">{row.decade} · {num(row.listens)}</span>
              {/each}
            </div>
          {/if}
          {#if unknownYear.listens > 0}
            <button
              type="button"
              class="mt-4 w-full flex items-center gap-3 text-left rounded-md px-2 py-1.5 min-h-9 transition-colors hover:bg-white/5 {filters.unknownYear ? 'bg-white/5' : ''}"
              aria-pressed={filters.unknownYear}
              title={$t('listening.toggleFilter')}
              onclick={() => apply(period, toggleYear(filters, UNKNOWN_YEAR))}
            >
              <span class="text-[11px] text-white w-32 sm:w-40 shrink-0 truncate {filters.unknownYear ? 'font-bold' : ''}">{$t('listening.unknownYear')}</span>
              <span class="h-2 flex-1 bg-white/5 rounded-full overflow-hidden">
                <span class="block h-full rounded-full {filters.unknownYear ? 'bg-brand' : 'bg-white/20'}" style="width: {(unknownYear.listens / Math.max(yearPeak, unknownYear.listens)) * 100}%"></span>
              </span>
              <span class="text-[11px] text-muma-spotify-text tabular-nums w-12 text-right shrink-0">{num(unknownYear.listens)}</span>
            </button>
          {/if}
          <p class="text-[10px] text-muma-spotify-subtle mt-3">{$t('listening.tapToFilter')}</p>
        {/if}
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-5">{$t('listening.clock')}</h2>
        <div class="flex items-end gap-0.5 h-32">
          {#each hours as count, hour (hour)}
            <div class="flex-1 flex flex-col justify-end h-full group relative">
              <div class="bg-brand/50 group-hover:bg-brand transition-colors rounded-t-sm" style="height: {(count / peak(hours.map((n) => ({ listens: n })))) * 100}%"></div>
              <div class="absolute -top-7 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                {String(hour).padStart(2, '0')}:00 — {num(count)}
              </div>
            </div>
          {/each}
        </div>
        <div class="flex justify-between mt-2 text-[10px] text-muma-spotify-subtle font-mono tabular-nums">
          <span>00:00</span><span>12:00</span><span>23:00</span>
        </div>
      </div>

      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-5">{$t('listening.weekdays')}</h2>
        <div class="flex flex-col gap-2.5">
          {#each weekdays as count, day (day)}
            <div class="flex items-center gap-3">
              <span class="text-[11px] text-muma-spotify-text w-8 shrink-0">{$t(`listening.weekday.${day}`)}</span>
              <div class="h-2 flex-1 bg-white/5 rounded-full overflow-hidden">
                <div class="h-full bg-brand rounded-full" style="width: {(count / peak(weekdays.map((n) => ({ listens: n })))) * 100}%"></div>
              </div>
              <span class="text-[11px] text-muma-spotify-text tabular-nums w-12 text-right shrink-0">{num(count)}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-1">{$t('listening.topTracks')}</h2>
        <p class="text-[10px] text-muma-spotify-subtle mb-4">{$t('listening.matchedOnlyNote')}</p>
        {#if topTracks.length === 0}
          <p class="text-xs text-muma-spotify-subtle">{$t('listening.empty')}</p>
        {:else}
          <ol class="flex flex-col gap-2.5">
            {#each topTracks as track, index (track.track_id)}
              <li class="flex items-center gap-3">
                <span class="text-[11px] text-muma-spotify-subtle tabular-nums w-4 shrink-0">{index + 1}</span>
                <span class="flex-1 min-w-0">
                  <span class="block text-xs text-white font-bold truncate">{track.title}</span>
                  <span class="block text-[11px] text-muma-spotify-text truncate">{track.artist ?? $t('listening.unknownArtist')}</span>
                </span>
                <span class="text-xs text-muma-spotify-text tabular-nums shrink-0">{num(track.listens)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>

      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-1">{$t('listening.topArtists')}</h2>
        <p class="text-[10px] text-muma-spotify-subtle mb-4">{$t('listening.matchedOnlyNote')}</p>
        {#if topArtists.length === 0}
          <p class="text-xs text-muma-spotify-subtle">{$t('listening.empty')}</p>
        {:else}
          <ol class="flex flex-col gap-2.5">
            {#each topArtists as artist, index (artist.artist_id)}
              <li class="flex items-center gap-3">
                <span class="text-[11px] text-muma-spotify-subtle tabular-nums w-4 shrink-0">{index + 1}</span>
                <button
                  class="flex-1 min-w-0 text-left text-xs text-white font-bold truncate hover:underline"
                  onclick={() => onnavigate?.(`artist:${artist.artist_id}`)}
                >{artist.artist}</button>
                <span class="text-xs text-muma-spotify-text tabular-nums shrink-0">{num(artist.listens)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>

      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-1 flex items-center gap-1.5">
          <Tag size={13} class="text-brand" /> {$t('listening.topLabels')}
        </h2>
        <p class="text-[10px] text-muma-spotify-subtle mb-4">{$t('listening.labelsNote')}</p>
        {#if topLabels.length === 0}
          <p class="text-xs text-muma-spotify-subtle">{$t('listening.empty')}</p>
        {:else}
          <ol class="flex flex-col gap-2.5">
            {#each topLabels as label, index (label.label_id)}
              <li class="flex items-center gap-3">
                <span class="text-[11px] text-muma-spotify-subtle tabular-nums w-4 shrink-0">{index + 1}</span>
                <button
                  class="flex-1 min-w-0 text-left text-xs text-white font-bold truncate hover:underline"
                  onclick={() => onnavigate?.(`label:${label.label}`)}
                >{label.label}</button>
                <span class="text-xs text-muma-spotify-text tabular-nums shrink-0">{num(label.listens)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>
    </div>

    {#if sources.length > 0}
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-1 flex items-center gap-1.5">
          <Radio size={13} class="text-brand" /> {$t('listening.sources')}
        </h2>
        <p class="text-[10px] text-muma-spotify-subtle mb-4">{$t('listening.sourcesNote')}</p>
        <div class="flex flex-col gap-2.5">
          {#each sources as row (row.source)}
            <div class="flex items-center gap-3">
              <span class="text-[11px] text-white w-40 shrink-0 truncate">{row.source}</span>
              <div class="h-2 flex-1 bg-white/5 rounded-full overflow-hidden">
                <div class="h-full bg-brand rounded-full" style="width: {(row.listens / peak(sources)) * 100}%"></div>
              </div>
              <span class="text-[11px] text-muma-spotify-text tabular-nums w-16 text-right shrink-0">{num(row.listens)}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>
