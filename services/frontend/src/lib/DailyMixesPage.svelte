<script>
  import { t } from './i18n/index.js';
  import { authParams } from './store.js';
  import { loadDailyMixCards } from './dailyMixes.js';
  import DailyMixCard from './DailyMixCard.svelte';

  /**
   * The phone's own "Daily mixes" page: reached by tapping the Home tile when the account's
   * daily-mix section is set to "Knop". A vertical list of the same five cards the desktop shelf
   * and the phone's own overview shelf draw, each already playable from here.
   */
  const { onnavigate } = $props();

  let cards = $state([]);
  let loaded = $state(false);

  $effect(() => {
    const auth = $authParams;
    let active = true;
    loadDailyMixCards(auth).then((built) => {
      if (!active) return;
      cards = built.cards;
      loaded = true;
      void built.refine((updated) => {
        if (active) cards = cards.map((card) => (card.slug === updated.slug ? updated : card));
      });
    });
    return () => { active = false; };
  });
</script>

<div class="flex flex-col gap-6 pb-12">
  <h1 class="text-3xl font-black">{$t('nav.dailyMixes')}</h1>
  {#if !loaded}
    <p class="text-muma-spotify-text">{$t('common.loading')}</p>
  {:else if cards.length === 0}
    <p class="text-muma-spotify-text">{$t('dashboard.noTracksInSection')}</p>
  {:else}
    <div class="grid grid-cols-2 gap-3">
      {#each cards as card (card.slug)}
        <DailyMixCard
          slug={card.slug}
          title={card.title}
          subtitle={card.subtitle}
          color={card.color}
          cover={card.cover}
          onopen={onnavigate}
        />
      {/each}
    </div>
  {/if}
</div>
