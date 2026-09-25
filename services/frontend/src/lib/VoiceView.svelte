<script>
  import { t } from './i18n/index.js';
  import { QUALITY_LABEL_KEYS } from './quality.js';
  import { onMount, onDestroy } from 'svelte';
  import { platform as defaultPlatform } from './platform/index.js';
  import { currentTrack, playerState } from './store.js';
  import { startQueue } from './queue.js';
  import { listOf, subsonicJson } from './subsonic.js';

  /**
   * MuMa's own voice entry point on the web, over `platform.speech`.
   *
   * The microphone and the text are the only things this screen owns. Everything a word could mean
   * -- the genre, the artist, the year, "did you mean the album or the playlist" -- is decided by
   * `core/voice` on the Kotlin side, through `MumaSpeechPlugin.interpret`; this component only ever
   * renders what came back and, for a clear command, plays it through the same path a preset or a
   * Home card uses (`subsonicJson` + `queue.js`'s `startQueue`). It never asks the
   * platform to play anything itself.
   *
   * Reachable from the phone's Search tab (a microphone button, hidden when `platform.speech` is
   * not `supported`), from `shellRoutes.js`'s `voice` route -- the quick-settings tile, the launcher
   * shortcut, a car-mode microphone -- and by a direct link, where it renders the same "not
   * available" message the entry points hide themselves on.
   */
  const { platform = defaultPlatform } = $props();

  /** What `subsonicJson('getSongs', ...)` is asked for; the same size a preset asks for. */
  const PAGE_SIZE = 500;

  /** @typedef {'idle'|'listening'|'working'|'play'|'ask'|'nothing'|'error'} Phase */

  /** @type {Phase} */
  let phase = $state('idle');
  let partial = $state('');
  /** The text most recently sent to `interpret()`, so a tapped question option can answer it. */
  let heardText = $state('');
  /** @type {Record<string, string>|null} */
  let explanation = $state(null);
  /** @type {{prompt: string, options: string[]}|null} */
  let question = $state(null);

  let showCommands = $state(false);
  /** @type {{title: string, html: string}|null} */
  let commands = $state(null);

  let showDiagnostics = $state(false);
  let diagnosticsLoaded = $state(false);
  /** @type {Array<{summary: string, lines: Array<{label: string, text: string}>}>} */
  let diagnosticsTraces = $state([]);

  let unsubscribePartial = null;
  let unsubscribeFinal = null;

  const supported = $derived(platform?.speech?.supported === true);

  /** The rows worth printing under "explanation", in a fixed, readable order. */
  const FIELD_ORDER = ['genre', 'label', 'artist', 'album', 'playlist', 'year', 'rating', 'quality', 'sets', 'order'];

  onMount(() => {
    if (!supported) return;
    unsubscribePartial = platform.speech.onPartial(({ text }) => {
      partial = text ?? '';
    });
    unsubscribeFinal = platform.speech.onFinal(({ text, alternatives }) => {
      partial = '';
      runInterpret(text ?? '', (alternatives ?? []).map((a) => a.text));
    });
    listen();
  });

  onDestroy(() => {
    unsubscribePartial?.();
    unsubscribeFinal?.();
    try {
      platform?.speech?.stop?.();
    } catch {
      // Nothing to do about a shell that failed to stop a recogniser that is going away anyway.
    }
  });

  /**
   * Opens the microphone. A repeat button, not a start button -- see the class doc.
   *
   * @param {{silent?: boolean}} [options] `silent` is set only for the re-listen after a question
   *   goes up: the chips are already the answer on screen, and switching the phase back to
   *   "listening" would take them off it before anyone had a chance to tap one.
   */
  async function listen({ silent = false } = {}) {
    if (!supported) return;
    partial = '';
    if (!silent) phase = 'listening';
    try {
      await platform.speech.start();
    } catch (error) {
      console.error('Could not start listening', error);
      if (!silent) phase = 'error';
    }
  }

  function micTapped() {
    if (phase === 'listening') {
      platform.speech.stop();
      phase = 'idle';
      return;
    }
    listen();
  }

  /**
   * Runs [text] through `interpret()` and acts on what came back: plays a clear command, puts up a
   * question, or shows why nothing could be run. Never throws into the caller.
   *
   * @param {string} text
   * @param {string[]} [hypotheses]
   * @param {string} [pinned] A kind the user chose after being asked.
   */
  async function runInterpret(text, hypotheses = [], pinned) {
    if (!text.trim()) {
      phase = 'idle';
      return;
    }
    heardText = text;
    phase = 'working';

    let result;
    try {
      result = await platform.speech.interpret({ text, hypotheses, pinned });
    } catch (error) {
      console.error('Voice interpret failed', error);
      explanation = { heard: text, reason: $t('common.unknownError') };
      question = null;
      phase = 'nothing';
      return;
    }

    explanation = result?.explanation ?? { heard: text };
    const resolution = result?.resolution ?? { kind: 'nothing' };
    diagnosticsLoaded = false;

    if (resolution.kind === 'play') {
      question = null;
      await play(resolution.query);
    } else if (resolution.kind === 'ask') {
      question = resolution.question ?? null;
      phase = 'ask';
      // The chips are the reliable half, the microphone the convenient one; a car park is a bad
      // place to look at a screen and a quiet room is a bad place to talk, so both stay open.
      listen({ silent: true });
    } else {
      question = null;
      phase = 'nothing';
    }
  }

  /**
   * Runs the resolved query through the same path a preset or a Home card uses, and starts it.
   *
   * @param {import('./platform/index.js').VoiceQuery|undefined} query
   */
  async function play(query) {
    let tracks = [];
    try {
      if (query?.type === 'filtered') {
        const data = await subsonicJson(query.method ?? 'getSongs', {
          ...query.params,
          count: PAGE_SIZE,
        });
        tracks = listOf(data, 'songs.song');
      } else if (query?.type === 'item' && query.kind === 'album') {
        tracks = listOf(await subsonicJson('getAlbum', { id: query.id }), 'album.song');
      } else if (query?.type === 'item' && query.kind === 'playlist') {
        tracks = listOf(await subsonicJson('getPlaylist', { id: query.id }), 'playlist.entry');
      }
    } catch (error) {
      console.error('Could not load what the voice query resolved to', error);
    }

    if (tracks.length === 0) {
      phase = 'nothing';
      explanation = { ...(explanation ?? {}), reason: $t('voice.noMatch', { query: heardText }) };
      return;
    }

    // No human name to give this one; startQueue still records the 'voice' view itself, which
    // resolves to nothing printable, so the header falls back to the track's own album.
    startQueue(tracks);
    currentTrack.set(tracks[0]);
    playerState.update((s) => ({ ...s, playing: true }));
    phase = 'play';
  }

  /** A tapped question option pins the kind and re-runs the same resolver, not a shortcut around it. */
  function answer(option) {
    runInterpret(heardText, [], option);
  }

  function again() {
    explanation = null;
    question = null;
    listen();
  }

  async function toggleCommands() {
    showCommands = !showCommands;
    if (showCommands && !commands) {
      try {
        commands = await platform.speech.vocabulary();
      } catch (error) {
        console.error('Could not load what MuMa Voice understands', error);
        commands = { title: '', html: '' };
      }
    }
  }

  async function toggleDiagnostics() {
    showDiagnostics = !showDiagnostics;
    if (showDiagnostics && !diagnosticsLoaded) {
      diagnosticsLoaded = true;
      try {
        const result = await platform.speech.trace();
        diagnosticsTraces = result?.traces ?? [];
      } catch (error) {
        console.error('Could not load the voice diagnostics', error);
        diagnosticsTraces = [];
      }
    }
  }

  function kindLabel(kind) {
    switch (kind) {
      case 'genre':
        return $t('voice.kindGenre');
      case 'label':
        return $t('voice.kindLabel');
      case 'artist':
        return $t('voice.kindArtist');
      case 'album':
        return $t('voice.kindAlbum');
      case 'playlist':
        return $t('voice.kindPlaylist');
      default:
        return kind;
    }
  }

  function fieldLabel(field) {
    switch (field) {
      case 'year':
        return $t('filter.year');
      case 'rating':
        return $t('filter.rating');
      case 'quality':
        return $t('filter.quality.label');
      case 'sets':
        return $t('voice.setsLabel');
      case 'order':
        return $t('filter.sortBy');
      default:
        return kindLabel(field);
    }
  }

  function fieldValue(field, value) {
    if (field === 'quality') return $t(QUALITY_LABEL_KEYS[value] ?? value);
    if (field !== 'order') return value;
    if (value === 'added') return $t('voice.orderAdded');
    if (value === 'random') return $t('voice.orderRandom');
    return $t('voice.orderReleased');
  }

  /** The explanation's naming rows, in a fixed order, skipping the ones rendered elsewhere. */
  function rowsOf(current) {
    if (!current) return [];
    return FIELD_ORDER.filter((field) => field in current).map((field) => ({
      field,
      label: fieldLabel(field),
      value: fieldValue(field, current[field]),
    }));
  }

  /** A string resource's `\n` becomes a line break; the `<b>` tags in it are already trusted markup. */
  function toHtml(text) {
    return (text ?? '').replace(/\n/g, '<br/>');
  }
</script>

<div class="flex flex-col gap-8 pb-12 items-center text-center">
  <h1 class="text-2xl font-black">{$t('voice.title')}</h1>

  {#if !supported}
    <p class="text-muma-spotify-text max-w-sm">{$t('voice.unsupported')}</p>
  {:else}
    <button
      type="button"
      class="w-24 h-24 rounded-full flex items-center justify-center shadow-xl border-none cursor-pointer transition
        {phase === 'listening' ? 'bg-brand text-black animate-pulse' : 'bg-muma-spotify-light text-white hover:bg-muma-spotify-hover'}"
      onclick={micTapped}
      aria-label={$t('voice.mic')}
    >
      <svg viewBox="0 0 24 24" width="40" height="40" fill="currentColor" aria-hidden="true">
        <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3z"></path>
        <path d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.93V20H8a1 1 0 1 0 0 2h8a1 1 0 1 0 0-2h-3v-2.07A7 7 0 0 0 19 11z"></path>
      </svg>
    </button>

    <div class="min-h-8">
      {#if phase === 'listening'}
        <p class="text-muma-spotify-text">{partial || $t('voice.listening')}</p>
      {:else if phase === 'working'}
        <p class="text-muma-spotify-text">{$t('voice.working')}</p>
      {:else if phase === 'error'}
        <p class="text-muma-spotify-text">{$t('voice.needsMicrophone')}</p>
      {:else if phase === 'idle'}
        <p class="text-muma-spotify-text">{$t('voice.prompt')}</p>
      {/if}
    </div>

    {#if explanation}
      <div class="w-full max-w-sm bg-muma-spotify-panel rounded-lg p-4 text-left flex flex-col gap-2" data-testid="voice-explanation">
        {#if explanation.heard}
          <div>
            <span class="text-xs uppercase tracking-wider text-muma-spotify-text">{$t('voice.heard')}</span>
            <p class="text-white">“{explanation.heard}”</p>
          </div>
        {/if}

        {#if explanation.understood}
          <div>
            <span class="text-xs uppercase tracking-wider text-muma-spotify-text">{$t('voice.understood')}</span>
            <p class="text-white">{explanation.understood}</p>
          </div>
        {/if}

        {#each rowsOf(explanation) as row (row.field)}
          <div class="flex justify-between text-sm">
            <span class="text-muma-spotify-text">{row.label}</span>
            <span class="text-white">{row.value}</span>
          </div>
        {/each}

        {#if explanation.reason}
          <p class="text-muma-spotify-text text-sm">{explanation.reason}</p>
        {/if}
      </div>
    {/if}

    {#if phase === 'ask' && question}
      <div class="flex flex-col gap-3 items-center" data-testid="voice-question">
        <p class="text-white">{$t('voice.ask', { term: question.prompt })}</p>
        <div class="flex flex-wrap gap-2 justify-center">
          {#each question.options as option (option)}
            <button
              type="button"
              class="px-4 py-2 rounded-full bg-muma-spotify-light text-white border-none cursor-pointer hover:bg-muma-spotify-hover"
              onclick={() => answer(option)}
            >
              {kindLabel(option)}
            </button>
          {/each}
        </div>
      </div>
    {/if}

    {#if phase === 'play'}
      <p class="text-white">{$t('voice.playing', { what: explanation?.understood ?? heardText })}</p>
    {/if}

    {#if phase === 'nothing' || phase === 'play'}
      <button
        type="button"
        class="px-6 py-2 rounded-full bg-transparent border border-muma-spotify-text text-white cursor-pointer hover:border-white"
        onclick={again}
      >
        {$t('voice.again')}
      </button>
    {/if}

    <button type="button" class="bg-transparent border-none text-muma-spotify-text underline cursor-pointer" onclick={toggleCommands}>
      {$t('voice.commandsLink')}
    </button>

    {#if showCommands && commands}
      <div class="w-full max-w-sm bg-muma-spotify-panel rounded-lg p-4 text-left text-sm text-muma-spotify-text" data-testid="voice-commands">
        {#if commands.title}<h2 class="text-white font-bold mb-2">{commands.title}</h2>{/if}
        <div>{@html toHtml(commands.html)}</div>
      </div>
    {/if}

    <button type="button" class="bg-transparent border-none text-muma-spotify-text underline cursor-pointer" onclick={toggleDiagnostics}>
      {$t('voice.diagnosticsTitle')}
    </button>

    {#if showDiagnostics}
      <div class="w-full max-w-sm text-left text-sm text-muma-spotify-text" data-testid="voice-diagnostics">
        {#if diagnosticsTraces.length === 0}
          <p>{$t('voice.diagnosticsEmpty')}</p>
        {:else}
          {#each diagnosticsTraces as trace, index (index)}
            <p class="border-b border-muma-spotify-light py-2">{trace.summary}</p>
          {/each}
        {/if}
      </div>
    {/if}
  {/if}
</div>
