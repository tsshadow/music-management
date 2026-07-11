<script>
  import { onMount } from 'svelte';
  import { deduplicateEnabled, authParams, credentials } from '../store.js';

  let settings = $state({
    uiArtistReleaseSortMethod: 107,
    uiEnableInlineArtistRelationships: false,
    uiInlineArtistRelationships: [2, 6], // Composer, Performer
    uiTranscodingMode: 2,
    uiTranscodingFormat: 2,
    uiTranscodingBitrate: 128000,
    uiReplayGainMode: 0,
    uiReplayGainPreAmpGain: 0,
    uiReplayGainPreAmpGainIfNoInfo: 0,
    scrobblingBackend: 0,
    mumaScrobblingEnabled: true,
    feedbackBackend: 0,
    listenbrainzToken: '',
    subsonicToken: '',
    subsonicEnableTranscodingByDefault: false,
    subsonicDefaultTranscodeFormat: 2,
    subsonicDefaultTranscodeBitrate: 128000,
    subsonicArtistListMode: 0
  });

  let isLoading = $state(true);
  let isSaving = $state(false);
  let message = $state('');

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
          uiArtistReleaseSortMethod: parseInt(user.uiArtistReleaseSortMethod) || 107,
          uiEnableInlineArtistRelationships: user.uiEnableInlineArtistRelationships === true || user.uiEnableInlineArtistRelationships === 'true',
          uiInlineArtistRelationships: (user.uiInlineArtistRelationships || '').split(',').map(s => parseInt(s)).filter(n => !isNaN(n)),
          uiTranscodingMode: user.uiTranscodingMode !== undefined ? parseInt(user.uiTranscodingMode) : 2,
          uiTranscodingFormat: parseInt(user.uiTranscodingFormat) || 2,
          uiTranscodingBitrate: parseInt(user.uiTranscodingBitrate) || 128000,
          uiReplayGainMode: parseInt(user.uiReplayGainMode) || 0,
          uiReplayGainPreAmpGain: parseFloat(user.uiReplayGainPreAmpGain) || 0,
          uiReplayGainPreAmpGainIfNoInfo: parseFloat(user.uiReplayGainPreAmpGainIfNoInfo) || 0,
          scrobblingBackend: parseInt(user.scrobblingBackend) || 0,
          mumaScrobblingEnabled: user.mumaScrobblingEnabled === true || user.mumaScrobblingEnabled === 'true',
          feedbackBackend: parseInt(user.feedbackBackend) || 0,
          listenbrainzToken: user.listenbrainzToken || '',
          subsonicToken: user.subsonicToken || '',
          subsonicEnableTranscodingByDefault: user.subsonicEnableTranscodingByDefault === true || user.subsonicEnableTranscodingByDefault === 'true',
          subsonicDefaultTranscodeFormat: parseInt(user.subsonicDefaultTranscodeFormat) || 2,
          subsonicDefaultTranscodeBitrate: parseInt(user.subsonicDefaultTranscodeBitrate) || 128000,
          subsonicArtistListMode: parseInt(user.subsonicArtistListMode) || 0
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
    try {
      const params = new URLSearchParams();
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
        setTimeout(() => message = '', 3000);
      } else {
        message = 'Fout bij opslaan: ' + (data['subsonic-response']?.error?.message || 'Onbekende fout');
      }
    } catch (e) {
      message = 'Netwerkfout bij opslaan';
      console.error(e);
    } finally {
      isSaving = false;
    }
  }

  function toggleDeduplicate() {
    deduplicateEnabled.update(v => !v);
  }

  function toggleRole(roleId) {
    if (settings.uiInlineArtistRelationships.includes(roleId)) {
      settings.uiInlineArtistRelationships = settings.uiInlineArtistRelationships.filter(id => id !== roleId);
    } else {
      settings.uiInlineArtistRelationships = [...settings.uiInlineArtistRelationships, roleId];
    }
  }

  function regenSubsonicToken() {
    settings.subsonicToken = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
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
    <div class="mb-6 p-4 rounded bg-brand/10 border border-brand/20 text-brand text-center font-medium">
      {message}
    </div>
  {/if}

  <div class="flex flex-col gap-6">
    <!-- Interface Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Interface</h2>
      
      <div class="flex flex-col gap-6">
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
          <select bind:value={settings.uiArtistReleaseSortMethod} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
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
                    {#each artistRoles as role}
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
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Subsonic API & Externe Clients</h2>
      
      <div class="flex flex-col gap-6">
        <div class="flex flex-col gap-2">
            <h3 class="font-bold">Subsonic API Key (Token)</h3>
            <p class="text-xs text-[#b3b3b3] mb-2">Gebruik deze sleutel voor externe apps (zoals Magna of Ultrasonic) in plaats van je wachtwoord.</p>
            <div class="flex gap-2">
                <input 
                    type="text" 
                    readonly 
                    value={settings.subsonicToken} 
                    placeholder="Nog geen token gegenereerd"
                    class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none flex-1 font-mono text-sm"
                />
                <button onclick={regenSubsonicToken} class="bg-[#333] text-white px-4 py-2 rounded hover:bg-[#444] transition-colors text-sm font-bold">
                    Genereer Nieuw
                </button>
                <button onclick={() => settings.subsonicToken = ''} class="bg-red-500/20 text-red-500 px-4 py-2 rounded hover:bg-red-500/30 transition-colors text-sm font-bold">
                    Verwijder
                </button>
            </div>
        </div>

        <div class="grid grid-cols-2 gap-8 mt-4 pt-4 border-t border-white/5">
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">Artiestlijst Modus</h3>
                <p class="text-xs text-[#b3b3b3] mb-2">Hoe artiesten worden gegroepeerd in Subsonic apps.</p>
                <select bind:value={settings.subsonicArtistListMode} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
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
                <select bind:value={settings.subsonicDefaultTranscodeFormat} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
                    <option value={1}>MP3</option>
                    <option value={2}>OGG Opus</option>
                    <option value={3}>OGG Vorbis</option>
                </select>
            </div>
            <div class="flex flex-col gap-2">
                <h3 class="font-bold">Subsonic Bitrate</h3>
                <select bind:value={settings.subsonicDefaultTranscodeBitrate} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
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

    <!-- Audio Section -->
    <section class="bg-[#181818] rounded-lg p-6 shadow-lg border border-white/5">
      <h2 class="text-xl font-bold mb-6 border-b border-white/10 pb-2">Audio (Web Player)</h2>
      
      <div class="flex flex-col gap-6">
        <div class="grid grid-cols-2 gap-8">
          <div class="flex flex-col gap-2">
            <h3 class="font-bold">Transcoding Modus</h3>
            <p class="text-xs text-[#b3b3b3] mb-2">Wanneer moet audio worden omgezet?</p>
            <select bind:value={settings.uiTranscodingMode} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
              <option value={0}>Nooit (Direct Stream)</option>
              <option value={1}>Altijd</option>
              <option value={2}>Indien formaat niet ondersteund</option>
            </select>
          </div>

          <div class="flex flex-col gap-2">
            <h3 class="font-bold">Output Formaat</h3>
            <p class="text-xs text-[#b3b3b3] mb-2">Welke codec moet worden gebruikt?</p>
            <select bind:value={settings.uiTranscodingFormat} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
              <option value={1}>MP3</option>
              <option value={2}>OGG Opus (Aanbevolen)</option>
              <option value={3}>OGG Vorbis</option>
            </select>
          </div>
        </div>

        <div class="flex items-center justify-between">
          <div class="flex flex-col gap-1">
            <h3 class="text-lg font-bold">Bitrate</h3>
            <p class="text-sm text-[#b3b3b3]">Kwaliteit van de transcoding.</p>
          </div>
          <select bind:value={settings.uiTranscodingBitrate} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
            <option value={64000}>64 kbps</option>
            <option value={96000}>96 kbps</option>
            <option value={128000}>128 kbps</option>
            <option value={192000}>192 kbps</option>
            <option value={256000}>256 kbps</option>
            <option value={320000}>320 kbps</option>
          </select>
        </div>

        <div class="flex flex-col gap-4 mt-4 pt-4 border-t border-white/5">
          <div class="flex items-center justify-between">
            <div class="flex flex-col gap-1">
              <h3 class="text-lg font-bold">ReplayGain Modus</h3>
              <p class="text-sm text-[#b3b3b3]">Volume egalisatie.</p>
            </div>
            <select bind:value={settings.uiReplayGainMode} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
              <option value={0}>Uit</option>
              <option value={1}>Automatisch</option>
              <option value={2}>Track (Gelijk volume per nummer)</option>
              <option value={3}>Album (Behoud dynamiek album)</option>
            </select>
          </div>

          <div class="grid grid-cols-2 gap-8">
            <div class="flex flex-col gap-2">
              <h3 class="font-bold">Pre-amp Gain</h3>
              <p class="text-xs text-[#b3b3b3]">{settings.uiReplayGainPreAmpGain} dB</p>
              <input type="range" min="-15" max="15" step="0.5" bind:value={settings.uiReplayGainPreAmpGain} class="accent-brand" />
            </div>
            <div class="flex flex-col gap-2">
              <h3 class="font-bold">Fallback Gain</h3>
              <p class="text-xs text-[#b3b3b3]">{settings.uiReplayGainPreAmpGainIfNoInfo} dB (bij missende info)</p>
              <input type="range" min="-15" max="15" step="0.5" bind:value={settings.uiReplayGainPreAmpGainIfNoInfo} class="accent-brand" />
            </div>
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
          <select bind:value={settings.feedbackBackend} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
            <option value={0}>Intern</option>
            <option value={1}>ListenBrainz</option>
            <option value={2}>Muma Rating Service</option>
          </select>
        </div>

        <div class="flex flex-col gap-2">
          <h3 class="font-bold">Scrobbling Systeem</h3>
          <select bind:value={settings.scrobblingBackend} class="bg-[#282828] text-white px-4 py-2 rounded border border-white/10 outline-none focus:border-brand">
            <option value={0}>Intern</option>
            <option value={1}>ListenBrainz</option>
          </select>
        </div>

        <div class="flex items-center justify-between pt-4 border-t border-white/5">
            <div class="flex flex-col gap-1">
                <h3 class="font-bold">Muma Scrobbler</h3>
                <p class="text-xs text-[#b3b3b3]">Verstuur luistergegevens naar de centrale Muma database.</p>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" class="sr-only peer" bind:checked={settings.mumaScrobblingEnabled}>
                <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
            </label>
        </div>

        <div class="flex flex-col gap-2">
          <h3 class="font-bold">ListenBrainz User Token</h3>
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
