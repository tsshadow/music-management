/**
 * Voice input in a plain browser tab: none.
 *
 * The Web Speech API exists in some browsers, but the voice feature is the
 * phone's -- its parser and resolver live in `core/voice` on the Kotlin side --
 * so the browser reports `supported: false` rather than offering half of it.
 * The voice screen hides itself on that flag.
 */

const UNSUPPORTED = "Voice input is not available in the browser";

/** @type {import('../index.js').PlatformSpeech} */
const speech = {
  supported: false,

  /**
   * Starts listening.
   *
   * @param {{locale?: string}} [_options]
   * @returns {Promise<never>} Always rejects with {@link UNSUPPORTED}.
   */
  async start(_options) {
    throw new Error(UNSUPPORTED);
  },

  /** Stops listening. A no-op when nothing was ever started. */
  stop() {},

  /**
   * Text as it is being recognised.
   *
   * @param {function({text: string}): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onPartial(_handler) {
    return () => {};
  },

  /**
   * The recognised utterance, once.
   *
   * @param {function({text: string}): void} _handler
   * @returns {function(): void} Unsubscribes. Never fires here.
   */
  onFinal(_handler) {
    return () => {};
  },

  /**
   * @param {{text: string, hypotheses?: string[], entryPoint?: string, pinned?: string}} _options
   * @returns {Promise<never>} Always rejects with {@link UNSUPPORTED}. The voice screen hides its
   *   microphone on `supported`, so this is only ever reached by a direct link.
   */
  async interpret(_options) {
    throw new Error(UNSUPPORTED);
  },

  /**
   * @returns {Promise<{title: string, html: string}>} Empty; the "what MuMa understands" page is
   *   reached from the voice screen, which is not offered here either.
   */
  async vocabulary() {
    return { title: "", html: "" };
  },

  /** @returns {Promise<{traces: Array<object>}>} Empty; there is no request to have traced. */
  async trace() {
    return { traces: [] };
  },
};

export default speech;
