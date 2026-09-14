import { listen, fireAndForget } from "./listen.js";

/**
 * `platform.speech` inside the Android shell: `SpeechCapture`, the same
 * recogniser the Kotlin voice sheet and Android Auto use, through the
 * `MumaSpeech` plugin.
 *
 * Only the capture is native. The parser and the resolver stay in `core/voice`
 * and run on whatever text comes out, so the microphone remains one pipeline
 * however the screen around it is built.
 *
 * `supported` is a plain boolean in the contract -- a screen reads it while
 * deciding whether to render at all -- and the plugin answers asynchronously.
 * It therefore starts out `true`, which is right for every phone that has a
 * recogniser, and {@link loadSupported} corrects it during boot for the ones
 * that do not. A `start()` on a phone without one rejects either way.
 */

/**
 * Builds the shell's speech implementation.
 *
 * @param {object} plugin - The registered `MumaSpeech` plugin.
 * @returns {object} An implementation of the `platform.speech` interface.
 */
export function createCapacitorSpeech(plugin) {
  const speech = {
    supported: true,

    /**
     * Asks the plugin whether this phone has a recogniser at all, and records
     * the answer in `supported`.
     *
     * @returns {Promise<boolean>}
     */
    async loadSupported() {
      try {
        const answer = await plugin.supported();
        speech.supported = answer?.value === true;
      } catch (error) {
        console.warn("Could not ask whether speech is available", error);
        speech.supported = false;
      }
      return speech.supported;
    },

    /**
     * Starts listening. Asks for the microphone permission first if it has to,
     * and rejects when the user refuses.
     *
     * @param {{locale?: string}} [options]
     * @returns {Promise<void>}
     */
    async start(options = {}) {
      await plugin.start(options ?? {});
    },

    /** Stops listening. */
    stop() {
      fireAndForget("speech.stop", plugin.stop());
    },

    /**
     * Text as it is being recognised.
     *
     * @param {function({text: string}): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    onPartial(handler) {
      return listen(plugin, "partial", (event) => handler({ text: event?.text ?? "" }));
    },

    /**
     * The recognised utterance.
     *
     * `alternatives` is the rest of what the recogniser heard, best first. The
     * resolver walks all of them, because the reading the recogniser preferred
     * is often not the one the library can place.
     *
     * @param {function({text: string, alternatives: Array<object>}): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    onFinal(handler) {
      return listen(plugin, "final", (event) =>
        handler({
          text: event?.text ?? "",
          alternatives: Array.isArray(event?.alternatives) ? event.alternatives : [],
        }),
      );
    },

    /**
     * A recogniser error, as a `SpeechRecognizer.ERROR_*` code. Native only;
     * the browser has no recogniser to fail.
     *
     * @param {function({code: number}): void} handler
     * @returns {function(): void} Unsubscribes.
     */
    onError(handler) {
      return listen(plugin, "error", (event) => handler({ code: event?.code ?? 0 }));
    },

    /**
     * Runs text through `core/voice`'s parser and resolver, unchanged, and answers with what it
     * found. Never plays anything -- see the `interpret` doc in `platform/index.js`.
     *
     * @param {{text: string, hypotheses?: string[], entryPoint?: string, pinned?: string}} options
     * @returns {Promise<import('../index.js').VoiceResolution>}
     */
    async interpret({ text, hypotheses = [], entryPoint, pinned } = {}) {
      return await plugin.interpret({ text, hypotheses, entryPoint, pinned });
    },

    /** What the "what MuMa understands" page shows. */
    async vocabulary() {
      return await plugin.vocabulary();
    },

    /** The recent voice requests, newest first. */
    async trace() {
      return await plugin.trace();
    },
  };

  return speech;
}
