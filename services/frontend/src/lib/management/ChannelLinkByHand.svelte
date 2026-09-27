<!--
  The "Handmatig koppelen" panel at the top of Beheer -> Downloaders -> Koppelingen: link a channel
  the search proposed nothing for to a label or an approved artist, picked by typing part of either
  name. `initialChannel` preselects the channel when the panel is opened from a row of the
  Volledigheid table. See docs/designs/channel-links/functional.md, "Linking by hand".
-->
<script>
  import { t } from '../i18n/index.js';
  import { Link2 } from '@lucide/svelte';
  import SinglePicker from '../SinglePicker.svelte';
  import { KINDS, kindLabel, describeChannel, firstUnlinkedKind, handLinkMessage } from './channelLinks.js';

  let { API_BASE, getHeaders, onMessage = () => {}, onError = () => {}, onLinked = () => {}, initialChannel = null } = $props();

  const PLATFORM_LABELS = { soundcloud: 'SoundCloud', youtube: 'YouTube' };
  const SEARCH_LIMIT = 20;

  let channel = $state(null);
  let kind = $state('label');
  let target = $state(null);
  let busy = $state(false);

  // A row of the Volledigheid table handed a channel over: start from it, on the kind it lacks.
  $effect(() => {
    if (initialChannel) {
      channel = initialChannel;
      kind = firstUnlinkedKind(initialChannel);
      target = null;
    }
  });

  const existing = $derived(channel?.[kind] ?? null);

  /** The API's own explanation when it gave one, so a refusal says why. */
  async function reasonFor(res) {
    const detail = await res.json().catch(() => ({}));
    return detail.detail || `HTTP ${res.status}`;
  }

  async function searchChannels(query) {
    const params = new URLSearchParams({ q: query, limit: String(SEARCH_LIMIT) });
    const res = await fetch(`${API_BASE}/api/channel-links/channels?${params}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await reasonFor(res));
    return res.json();
  }

  async function searchTargets(query) {
    const params = new URLSearchParams({ kind, q: query, limit: String(SEARCH_LIMIT) });
    const res = await fetch(`${API_BASE}/api/channel-links/targets?${params}`, { headers: getHeaders() });
    if (!res.ok) throw new Error(await reasonFor(res));
    return res.json();
  }

  function pickChannel(record) {
    channel = record;
    target = null;
    if (record) kind = firstUnlinkedKind(record);
  }

  function pickKind(next) {
    kind = next;
    target = null;
  }

  async function submit() {
    if (!channel || !target || busy) return;
    busy = true;
    try {
      const res = await fetch(`${API_BASE}/api/channel-links/channels/${channel.id}/${kind}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ target_id: target.id })
      });
      if (!res.ok) throw new Error(await reasonFor(res));
      const body = await res.json();
      onMessage(handLinkMessage(body, channel.name));
      channel = { ...channel, [kind]: { id: body.target_id, name: body.target_name } };
      target = null;
      onLinked(body);
    } catch (e) {
      onError(e.message);
    } finally {
      busy = false;
    }
  }
</script>

<section class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-6 space-y-4" aria-labelledby="channel-hand-link-title">
  <div>
    <h3 id="channel-hand-link-title" class="text-lg font-bold flex items-center gap-2"><Link2 size={18} /> {$t('management.downloaders.links.byHand.title')}</h3>
    <p class="text-muma-spotify-text text-sm max-w-3xl mt-1">{$t('management.downloaders.links.byHand.help')}</p>
  </div>

  <div class="grid gap-4 md:grid-cols-[1fr_auto_1fr_auto] md:items-end">
    <SinglePicker
      id="channel-hand-link-channel"
      label={$t('management.downloaders.links.byHand.channel')}
      placeholder={$t('management.downloaders.links.byHand.channelPlaceholder')}
      selected={channel}
      onsearch={searchChannels}
      onselect={pickChannel}
      describe={(record) => describeChannel(record, PLATFORM_LABELS)}
      disabled={busy}
    />

    <div class="flex flex-col gap-2">
      <span class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text" id="channel-hand-link-kind">{$t('management.downloaders.links.byHand.kind')}</span>
      <div class="flex gap-2" role="radiogroup" aria-labelledby="channel-hand-link-kind">
        {#each KINDS as option (option)}
          <button
            type="button"
            role="radio"
            aria-checked={kind === option}
            onclick={() => pickKind(option)}
            disabled={busy}
            class="text-sm font-bold px-4 py-2 rounded-full border transition-colors {kind === option ? 'bg-white text-black border-white' : 'bg-transparent text-white border-muma-spotify-muted hover:border-white'}"
          >
            {kindLabel(option)}
          </button>
        {/each}
      </div>
    </div>

    {#key kind}
      <SinglePicker
        id="channel-hand-link-target"
        label={$t('management.downloaders.links.byHand.target')}
        placeholder={$t(kind === 'label' ? 'management.downloaders.links.byHand.targetPlaceholderLabel' : 'management.downloaders.links.byHand.targetPlaceholderArtist')}
        selected={target}
        onsearch={searchTargets}
        onselect={(record) => (target = record)}
        disabled={busy || !!existing}
      />
    {/key}

    <button
      type="button"
      onclick={submit}
      disabled={busy || !channel || !target || !!existing}
      class="flex items-center justify-center gap-2 text-sm font-bold bg-brand text-black rounded-full px-5 py-2 min-h-11 transition-transform hover:scale-105 disabled:opacity-50 disabled:hover:scale-100"
    >
      <Link2 size={14} /> {$t('management.downloaders.links.byHand.submit')}
    </button>
  </div>

  {#if existing}
    <p class="text-sm text-muma-spotify-text" role="status">{$t('management.downloaders.links.byHand.alreadyLinked', { name: existing.name })}</p>
  {/if}
</section>
