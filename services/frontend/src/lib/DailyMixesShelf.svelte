<script>
  import { t } from './i18n/index.js';
  import { authParams } from './store.js';
  import { fetchGenreTints } from './genreTints.js';
  import { loadDailyMixCards } from './dailyMixes.js';
  import DailyMixCard from './DailyMixCard.svelte';

  /**
   * The five daily mixes, as a Home row: soft, mid, hard, then the day's artist and label. Used
   * on both the desktop Home (in place of the old single "Daily mix" row) and the phone's own
   * Home when the account's daily-mix section is set to "Overzicht" -- one component so the two
   * always draw the same five cards in the same colours.
   */
  const { onnavigate } = $props();

  let cards = $state([]);
  let loaded = $state(false);

  $effect(() => {
    const auth = $authParams;
    let active = true;
    fetchGenreTints()
      .then((tints) => loadDailyMixCards(tints, auth))
      .then((built) => {
        if (!active) return;
        cards = built.cards;
        loaded = true;
        void built.refine((updated) => {
          if (active) cards = cards.map((card) => card.slug === updated.slug ? updated : card);
        });
      });
    return () => { active = false; };
  });
</script>

<section class="flex flex-col gap-4">
  <div class="flex justify-between items-end mb-4">
    <h2 class="text-2xl font-bold m-0">{$t('nav.dailyMixes')}</h2>
  </div>
  <div class="flex gap-3 overflow-x-auto scrollbar-hide -mx-4 px-4 pb-1">
    {#each cards as card (card.slug)}
      <div class="w-[150px] shrink-0">
        <DailyMixCard
          slug={card.slug}
          title={card.title}
          subtitle={card.subtitle}
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
