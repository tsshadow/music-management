<script>
  import { t } from '../i18n/index.js';
  import { activeView, isAdmin } from '../store.js';
  import { platform } from '../platform/index.js';
  import { paragraphsOf, sectionsFor } from '../help.js';

  /**
   * The manual, as a settings tab: every section `help.js` lists that applies to this
   * reader, each with its text from the locale files and, where the section is about a
   * place, a button that goes there. The tour at the top is the same `SetupWizard` a
   * first run opens, started by hand over every step rather than the pending ones.
   *
   * `onnavigate` is what the sidebar passes every settings page; the manual is the one
   * that uses it, because a manual that cannot take you to the thing it describes is a
   * poorer manual.
   */
  const { onnavigate = (view) => activeView.set(view) } = $props();

  const sections = $derived(
    sectionsFor({ native: platform.system.isNative, admin: $isAdmin === true }),
  );

  /** Anchors, so a link from elsewhere in the app can open one section. */
  const anchor = (id) => `help-${id}`;
</script>

<div class="settings-density p-0 max-w-4xl mx-auto pb-24" data-testid="help-page">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">{$t('help.title')}</h1>
    <p class="text-[#b3b3b3]">{$t('help.subtitle')}</p>
  </header>

  <div class="flex flex-col gap-6">
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <div class="flex flex-col gap-1">
        <h2 class="text-xl font-bold m-0">{$t('help.tour.title')}</h2>
        <p class="text-sm text-[#b3b3b3] m-0">{$t('help.tour.body')}</p>
      </div>
      <button
        type="button"
        class="shrink-0 bg-brand text-black font-bold text-sm px-5 py-2 rounded-full border-none cursor-pointer hover:scale-105 transition-transform"
        onclick={() => onnavigate('setup')}
      >
        {$t('help.tour.start')}
      </button>
    </section>

    <nav aria-label={$t('help.contents')} class="flex flex-wrap gap-2">
      {#each sections as section (section.id)}
        <a
          href={`#${anchor(section.id)}`}
          class="text-xs font-bold px-3 py-1.5 rounded-full bg-[#282828] text-[#b3b3b3] hover:text-white no-underline"
        >{$t(`help.${section.id}.title`)}</a>
      {/each}
    </nav>

    {#each sections as section (section.id)}
      <section id={anchor(section.id)} class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
        <h2 class="text-xl font-bold mb-4 border-b border-white/10 pb-2">{$t(`help.${section.id}.title`)}</h2>
        <div class="flex flex-col gap-3 text-sm text-[#e5e5e5] leading-relaxed">
          {#each paragraphsOf($t(`help.${section.id}.body`)) as paragraph, i (i)}
            <p class="m-0">{paragraph}</p>
          {/each}
        </div>
        {#if section.view}
          <button
            type="button"
            class="mt-5 bg-white/10 hover:bg-white/20 text-white font-bold text-sm px-4 py-2 rounded-full border-none cursor-pointer transition-colors"
            onclick={() => onnavigate(section.view)}
          >
            {$t('help.goThere', { place: $t(`help.${section.id}.title`) })}
          </button>
        {/if}
      </section>
    {/each}
  </div>
</div>

