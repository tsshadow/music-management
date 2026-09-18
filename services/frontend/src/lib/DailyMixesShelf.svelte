<script>
  import { t } from './i18n/index.js';
  import { authParams } from './store.js';
  import { loadDailyMixCards } from './dailyMixes.js';
  import { RELEASE_RADAR } from './feeds.js';
  import DailyMixCard from './DailyMixCard.svelte';

  /**
   * The personalised feeds as a Home row of cards: the release radar (when `radar`), then the
   * five daily mixes -- soft, mid, hard, the day's artist and label. Used on the desktop Home
   * and on the phone's own Home for whichever of the two the account shows as "Overzicht", so
   * every screen draws the same cards in the same colours.
   *
   * Cards only: no feed is fetched for its tracks here. What is behind a card loads when it is
   * opened (docs/designs/feeds/home-load.md). The heading follows what the row holds.
   */
  const { onnavigate, radar = false, mixes = true } = $props();

  let cards = $state([]);
  let loaded = $state(false);

  const headingKey = $derived(
    radar && mixes ? 'nav.forYou' : radar ? 'nav.releaseRadar' : 'nav.dailyMixes',
  );

  /** The radar's own subtitle is null until MuMa gives it one; the tile copy fills the line. */
  function subtitleOf(card) {
    if (card.slug === RELEASE_RADAR && !card.subtitle) return $t('dashboard.empty.releaseRadar');
    return card.subtitle;
  }

  $effect(() => {
    const auth = $authParams;
    let active = true;
    loadDailyMixCards(auth, { radar }).then((built) => {
      if (!active) return;
      cards = mixes ? built.cards : built.cards.filter((card) => card.slug === RELEASE_RADAR);
      loaded = true;
      void built.refine((updated) => {
        if (active) cards = cards.map((card) => (card.slug === updated.slug ? updated : card));
      });
    });
    return () => {
      active = false;
    };
  });
</script>

<section class="flex flex-col gap-4">
  <div class="flex justify-between items-end mb-4">
    <h2 class="text-2xl font-bold m-0">{$t(headingKey)}</h2>
  </div>
  <div class="flex gap-3 overflow-x-auto scrollbar-hide -mx-4 px-4 pb-1">
    {#each cards as card (card.slug)}
      <div class="w-[150px] shrink-0">
        <DailyMixCard
          slug={card.slug}
          title={card.title}
          subtitle={subtitleOf(card)}
          color={card.color}
          cover={card.cover}
          onopen={onnavigate}
        />
      </div>
    {/each}
    {#if loaded && cards.length === 0}
      <p class="text-[#b3b3b3]">{$t('dashboard.noTracksInSection')}</p>
    {/if}
  </div>
</section>
