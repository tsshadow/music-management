<script>
  import { onMount } from 'svelte';
  import { SvelteURLSearchParams } from 'svelte/reactivity';
  import { deduplicateEnabled, authParams, credentials } from '../store.js';
  import LanguageSetting from './LanguageSetting.svelte';

  // Server default for uiArtistReleaseSortMethod (ReleaseSortMethod::OriginalDateDesc).
  const DEFAULT_SORT_METHOD = 8;

  let settings = $state({
    uiArtistReleaseSortMethod: DEFAULT_SORT_METHOD,
    uiEnableInlineArtistRelationships: false,
    uiInlineArtistRelationships: [2, 6], // Composer, Performer
    feedbackBackend: 0,
    listenbrainzToken: '',
    subsonicEnableTranscodingByDefault: false,
    subsonicDefaultTranscodeFormat: 2,
    subsonicDefaultTranscodeBitrate: 128000,
    subsonicArtistListMode: 0
  });

  let isLoading = $state(true);
  let isSaving = $state(false);
  let message = $state('');
  let isError = $state(false);

  const artistRoles = [
    { id: 1, label: 'Arranger' },
    { id: 2, label: 'Composer' },
    { id: 3, label: 'Conductor' },
    { id: 4, label: 'Lyricist' },
    { id: 5, label: 'Mixer' },
    { id: 6, label: 'Performer' },
    { id: 7, label: 'Producer' },
    { id: 9, label: 'Remixer' },
    { id: 10, label: 'Writer' }
  ];

  /**
   * Reads an integer attribute, falling back only when it is absent or
   * unparseable -- a legitimate 0 must survive.
   *
   * @param {unknown} value
   * @param {number} fallback
   * @returns {number}
   */
  function toInt(value, fallback) {
    const parsed = parseInt(value);
    return Number.isNaN(parsed) ? fallback : parsed;
  }

  function toBool(value) {
    return value === true || value === 'true';
  }

  onMount(async () => {
    await fetchSettings();
  });

  async function fetchSettings() {
    isLoading = true;
    try {
      const resp = await fetch(`/rest/getUser?${$authParams}&username=${encodeURIComponent($credentials.username)}`);
      const data = await resp.json();
      const user = data['subsonic-response']?.user;
      if (user) {
        settings = {
          uiArtistReleaseSortMethod: toInt(user.uiArtistReleaseSortMethod, DEFAULT_SORT_METHOD),
          uiEnableInlineArtistRelationships: toBool(user.uiEnableInlineArtistRelationships),
          uiInlineArtistRelationships: (user.uiInlineArtistRelationships || '')
            .split(',')
            .map((s) => parseInt(s))
            .filter((n) => !isNaN(n)),
          feedbackBackend: toInt(user.feedbackBackend, 0),
          listenbrainzToken: user.listenbrainzToken || '',
          subsonicEnableTranscodingByDefault: toBool(user.subsonicEnableTranscodingByDefault),
          subsonicDefaultTranscodeFormat: toInt(user.subsonicDefaultTranscodeFormat, 2),
          subsonicDefaultTranscodeBitrate: toInt(user.subsonicDefaultTranscodeBitrate, 128000),
          subsonicArtistListMode: toInt(user.subsonicArtistListMode, 0)
        };
      }
    } catch (e) {
      console.error('Failed to fetch user settings', e);
    } finally {
      isLoading = false;
    }
  }

  async function saveSettings() {
    isSaving = true;
    message = '';
    isError = false;
    try {
      const params = new SvelteURLSearchParams();
      params.append('username', $credentials.username);

      Object.entries(settings).forEach(([k, v]) => {
        if (Array.isArray(v)) {
          params.append(k, v.join(','));
        } else {
          params.append(k, v);
        }
      });

      const resp = await fetch(`/rest/updateUser?${$authParams}&${params.toString()}`);
      const data = await resp.json();
      if (data['subsonic-response']?.status === 'ok') {
        message = 'Instellingen succesvol opgeslagen!';
        setTimeout(() => (message = ''), 3000);
      } else {
        isError = true;
        message = 'Fout bij opslaan: ' + (data['subsonic-response']?.error?.message || 'Onbekende fout');
      }
    } catch (e) {
      isError = true;
      message = 'Netwerkfout bij opslaan';
      console.error(e);
    } finally {
      isSaving = false;
    }
  }

  function toggleDeduplicate() {
    deduplicateEnabled.update((v) => !v);
  }

  function toggleRole(roleId) {
    if (settings.uiInlineArtistRelationships.includes(roleId)) {
      settings.uiInlineArtistRelationships = settings.uiInlineArtistRelationships.filter((id) => id !== roleId);
    } else {
      settings.uiInlineArtistRelationships = [...settings.uiInlineArtistRelationships, roleId];
    }
  }
</script>

<div class="p-8 max-w-4xl mx-auto pb-24">
  <header class="mb-8 flex justify-between items-end">
    <div>
      <h1 class="text-3xl font-bold mb-2">Algemene Instellingen</h1>
      <p class="text-[#b3b3b3]">Beheer de weergave en het gedrag van MuMa Spotify.</p>
    </div>
    <button
      onclick={saveSettings}
      disabled={isSaving || isLoading}
      class="bg-brand text-black font-bold py-3 px-8 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
    >
      {isSaving ? 'Opslaan...' : 'Wijzigingen opslaan'}
    </button>
  </header>

  {#if message}
    <div
      class="mb-6 p-4 rounded text-center font-medium {isError
        ? 'bg-red-500/10 border border-red-500/20 text-red-400'
        : 'bg-brand/10 border border-brand/20 text-brand'}"
    >
      {message}
    </div>
  {/if}

  <div class="flex flex-col gap-6">
    <!-- Interface Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Interface</h2>

      <div class="flex flex-col gap-6">
        <LanguageSetting />

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">Deduplicatie</h3>
            <p class="text-sm text-[#b3b3b3]">Verberg dubbele nummers op basis van artiest en titel.</p>
          </div>
          <label class="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" class="sr-only peer" checked={$deduplicateEnabled} onchange={toggleDeduplicate}>
            <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
          </label>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">Standaard Sortering Albums</h3>
            <p class="text-sm text-[#b3b3b3]">Hoe albums worden gesorteerd op de artiestpagina.</p>
          </div>
          <select bind:value={settings.uiArtistReleaseSortMethod} aria-label="Standaard sortering albums" class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
            <option value={2}>Naam</option>
            <option value={5}>Jaar (Oudste eerst)</option>
            <option value={6}>Jaar (Nieuwste eerst)</option>
            <option value={7}>Origineel Jaar (Oudste eerst)</option>
            <option value={8}>Origineel Jaar (Nieuwste eerst)</option>
          </select>
        </div>

        <div class="flex flex-col gap-4 mt-4 pt-4 border-t border-white/5">
            <div class="flex items-center justify-between">
                <div class="flex flex-col gap-1">
                    <h3 class="text-lg font-bold">Artiest Relaties</h3>
                    <p class="text-sm text-[#b3b3b3]">Toon extra rollen (zoals componist of remixer) direct bij de artiest.</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" class="sr-only peer" bind:checked={settings.uiEnableInlineArtistRelationships}>
                    <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
                </label>
            </div>

            {#if settings.uiEnableInlineArtistRelationships}
                <div class="flex flex-wrap gap-2 mt-2">
                    {#each artistRoles as role (role.id)}
                        <button
                            onclick={() => toggleRole(role.id)}
                            class="px-4 py-2 rounded-full text-xs font-bold transition-all {settings.uiInlineArtistRelationships.includes(role.id) ? 'bg-brand text-black' : 'bg-[#282828] text-white hover:bg-[#333]'}"
                        >
                            {role.label}
                        </button>
                    {/each}
                </div>
            {/if}
        </div>
      </div>
    </section>

    <!-- Subsonic Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Externe Clients (Subsonic)</h2>

      <p class="text-xs text-[#b3b3b3] mb-6">
        Een API-sleutel voor externe apps zoals Ultrasonic of Magna wordt door een beheerder uitgegeven via de
        beheerpagina.
      </p>

      <div class="flex flex-col gap-6">
        <div class="grid grid-cols-2 gap-8">
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">Artiestlijst Modus</h3>
                <p class="text-xs text-[#b3b3b3] mb-2">Hoe artiesten worden gegroepeerd in Subsonic apps.</p>
                <select bind:value={settings.subsonicArtistListMode} aria-label="Artiestlijst modus" class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
                    <option value={0}>Alle Artiesten</option>
                    <option value={1}>Release Artiesten</option>
                    <option value={2}>Track Artiesten</option>
                </select>
            </div>

            <div class="flex items-center justify-between">
                <div class="flex flex-col gap-1">
                    <h3 class="font-bold">Transcoding Standaard</h3>
                    <p class="text-xs text-[#b3b3b3]">Altijd transcoderen voor Subsonic clients?</p>
                </div>
                <label class="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" class="sr-only peer" bind:checked={settings.subsonicEnableTranscodingByDefault}>
                    <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
                </label>
            </div>
        </div>

        <div class="grid grid-cols-2 gap-8">
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">Subsonic Formaat</h3>
                <select bind:value={settings.subsonicDefaultTranscodeFormat} aria-label="Subsonic formaat" class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
                    <option value={1}>MP3</option>
                    <option value={2}>OGG Opus</option>
                    <option value={3}>OGG Vorbis</option>
                </select>
            </div>
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">Subsonic Bitrate</h3>
                <select bind:value={settings.subsonicDefaultTranscodeBitrate} aria-label="Subsonic bitrate" class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
                    <option value={64000}>64 kbps</option>
                    <option value={96000}>96 kbps</option>
                    <option value={128000}>128 kbps</option>
                    <option value={192000}>192 kbps</option>
                    <option value={256000}>256 kbps</option>
                    <option value={320000}>320 kbps</option>
                </select>
            </div>
        </div>
      </div>
    </section>

    <!-- Services Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Externe Diensten</h2>

      <div class="flex flex-col gap-6">
        <div class="flex flex-col gap-2">
          <h3 class="font-bold">Feedback (Rating) Systeem</h3>
          <select bind:value={settings.feedbackBackend} aria-label="Feedback systeem" class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
            <option value={0}>Intern</option>
            <option value={1}>ListenBrainz</option>
            <option value={2}>Muma Rating Service</option>
          </select>
        </div>

        <div class="flex flex-col gap-2">
          <h3 class="font-bold">ListenBrainz User Token</h3>
          <p class="text-xs text-[#b3b3b3] mb-2">
            Luistergegevens gaan voor iedereen naar de centrale Muma database. Vul hier alleen een token in als je
            daarnaast ook naar je eigen ListenBrainz-account wilt scrobbelen.
          </p>
          <input
            type="password"
            bind:value={settings.listenbrainzToken}
            placeholder="Je ListenBrainz User Token..."
            class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand w-full"
          />
        </div>
      </div>
    </section>
  </div>
</div>

<style>
  .bg-brand {
    background-color: #1ed760;
  }
  .text-brand {
    color: #1ed760;
  }
</style>
