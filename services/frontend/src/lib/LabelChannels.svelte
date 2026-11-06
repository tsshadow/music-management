<script>
  /**
   * The label page's "Kanalen" section (issue #122): the SoundCloud, YouTube and Telegram
   * channels a curator linked to this label, with their track counts. Tapping one opens its
   * track list, or its page on the platform when the library has no list for it.
   *
   * Loads on its own (styleguide, Loading States: Granularity): card-shaped skeletons first
   * (curators; see `visible`), a section error with a retry when it fails, the last answer at
   * once on a revisit. A label nothing is linked to shows no section at all -- that is almost
   * every label -- except to a curator, who gets the way to Links to link one.
   *
   * @property {string} label - The label's name, as the route carries it.
   * @property {(view: string) => void} onnavigate - Opens a view (an album, a search).
   * @property {() => void} [onmanage] - Opens Management > Downloaders > Links.
   * @property {boolean} [canManage] - Whether the user may (un)link channels.
   * @property {Object} [platform] - The platform shim; a source URL goes through `system.openUrl`.
   */
  import { Cloud, Send, TvMinimalPlay, Link2 } from '@lucide/svelte';
  import { t } from './i18n/index.js';
  import SectionState from './loading/SectionState.svelte';
  import Skeleton from './loading/Skeleton.svelte';
  import { platform as defaultPlatform } from './platform/index.js';
  import { PLATFORM_LABELS, cachedLabelChannels, channelDestination, fetchLabelChannels } from './labelChannels.js';

  const { label, onnavigate, onmanage, canManage = false, platform = defaultPlatform } = $props();

  const ICONS = { soundcloud: Cloud, youtube: TvMinimalPlay, telegram: Send };

  let channels = $state(/** @type {Array<Object>|null} */ (null));
  let status = $state(/** @type {'loading'|'error'|'ready'} */ ('loading'));
  let opening = $state(/** @type {number|null} */ (null));
  // Which label the rows on screen belong to: an answer for a label left behind is dropped.
  let current = '';

  async function load(name) {
    current = name;
    const cached = cachedLabelChannels(name);
    channels = cached ?? null;
    // A revisit shows the last answer and refreshes quietly; a first visit shows skeletons.
    status = cached ? 'ready' : 'loading';
    try {
      const fresh = await fetchLabelChannels(name);
      if (current !== name) return;
      channels = fresh;
      status = 'ready';
    } catch {
      if (current !== name) return;
      if (!cached) status = 'error';
    }
  }

  $effect(() => {
    load(label);
  });

  async function open(channel) {
    if (opening !== null) return;
    opening = channel.id;
    try {
      const destination = await channelDestination(channel);
      if ('url' in destination) {
        platform.system.openUrl(destination.url).catch((error) => console.warn('Could not open the channel', error));
      } else {
        onnavigate?.(destination.view);
      }
    } finally {
      opening = null;
    }
  }

  // A curator always sees the section: its skeleton, its error, or the way to link a channel.
  // Anyone else sees it once there is something to show (or a failure to say so): almost no
  // label has a channel, and a skeleton on every label page that then vanishes would move the
  // track list for nothing.
  const visible = $derived(
    canManage || status === 'error' || (status === 'ready' && (channels?.length ?? 0) > 0),
  );
</script>

{#if visible}
  <section class="flex flex-col gap-2 mb-4" data-testid="label-channels" aria-labelledby="label-channels-heading">
    <div class="flex items-center gap-3">
      <h3 id="label-channels-heading" class="text-base font-bold m-0">{$t('labelChannels.title')}</h3>
      {#if canManage && onmanage}
        <button
          class="ml-auto flex items-center gap-1.5 bg-transparent border-none text-xs font-bold text-muma-spotify-text hover:text-white cursor-pointer p-1 transition-colors"
          onclick={() => onmanage()}
          data-testid="label-channels-manage"
        >
          <Link2 size={14} aria-hidden="true" />
          {$t('labelChannels.manage')}
        </button>
      {/if}
    </div>
    <SectionState {status} onretry={() => load(label)}>
      {#snippet skeleton()}
        <div class="flex gap-2 overflow-hidden" role="status" aria-label={$t('common.loading')} data-testid="label-channels-skeleton">
          {#each [0, 1, 2] as i (i)}
            <Skeleton class="h-14 w-44 shrink-0 rounded-md" />
          {/each}
        </div>
      {/snippet}
      {#if channels && channels.length > 0}
        <ul class="flex gap-2 overflow-x-auto list-none m-0 p-0 pb-1" data-testid="label-channels-list">
          {#each channels as channel (channel.id)}
            {@const Icon = ICONS[channel.platform] ?? Cloud}
            <li class="shrink-0">
              <button
                class="flex items-center gap-3 h-14 max-w-64 px-3 rounded-md bg-muma-spotify-light hover:bg-muma-spotify-hover border-none text-left cursor-pointer transition-colors {opening === channel.id ? 'opacity-50' : ''}"
                onclick={() => open(channel)}
                aria-busy={opening === channel.id}
                title={PLATFORM_LABELS[channel.platform] ?? channel.platform}
                data-testid="label-channel"
              >
                <Icon size={20} class="shrink-0 text-muma-spotify-text" aria-label={PLATFORM_LABELS[channel.platform] ?? channel.platform} />
                <span class="flex flex-col min-w-0">
                  <span class="text-sm font-bold text-white truncate">{channel.name}</span>
                  <span class="text-xs text-muma-spotify-text truncate">{$t('common.trackCount', { count: channel.track_count })}</span>
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="text-sm text-muma-spotify-text m-0" data-testid="label-channels-empty">{$t('labelChannels.none')}</p>
      {/if}
    </SectionState>
  </section>
{/if}
