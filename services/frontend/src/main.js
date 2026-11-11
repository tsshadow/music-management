import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { platform } from "./lib/platform/index.js";
import { bootstrapShell } from "./lib/nativeSession.js";
import { serverScreen } from "./lib/serverAddress.js";
import { askServerDecision } from "./lib/bootUnreachable.js";
import { watchServerReturn } from "./lib/offlineMode.js";
import { notify } from "./lib/notifications.js";
import { get } from "svelte/store";
import { dismissBootScreen, setBootStage } from "./lib/bootScreen.js";
import { logError, identifyBundle } from "./lib/diagnosticsLog.js";
import { initialState, installChunkReload, preloadLikelyNext } from "./lib/bootChunks.js";
import { preloadState } from "./lib/lazyViews.js";
import { localeReady, t } from "./lib/i18n/index.js";

const target = document.querySelector("#app");

// Whatever the WebView's own error handling missed. Forwarded into the same
// action trail a crash report reads, so a report says what the user did
// *and* what broke, in the order it happened; a browser tab has no such
// report and gets a console.error instead -- see `logError`.
window.addEventListener("error", (event) => {
  logError(event.error ?? event.message);
});
window.addEventListener("unhandledrejection", (event) => {
  logError(event.reason, { action: "js.unhandledRejection" });
});

// A tab left open over a deploy asks for chunks the server no longer has; reload once to
// pick up the new index.html instead of showing a retry pill that can never succeed.
installChunkReload(window);

// Fire-and-forget: nothing here gates the first render, and a report is
// still useful without an answer -- see `identifyBundle`.
identifyBundle();

// The locale file is its own chunk: start fetching it now, alongside the shell's bootstrap,
// rather than after it. `mountApp` waits for the same promise.
localeReady();

/**
 * In a browser the app mounts as soon as the chunk the URL needs is in (see below), and the
 * boot screen leaves with the first frame.
 *
 * Inside the Android shell the app is mounted only after the phone's server and
 * session have reached the stores -- the first component to render otherwise
 * fetches against `https://localhost`, which is the WebView and not a music
 * server. `bootstrapShell` never rejects, so a phone that cannot reach its
 * server still gets a login screen rather than a blank one. Meanwhile the boot
 * screen from index.html says which step it is on.
 *
 * The playback queue is not waited for (`deferQueue`, issue #113): its restore -- one lookup per
 * queued track -- runs behind the mounted app, with the mini player saying so, and a track the
 * listener starts first cancels it (`queueRestore.js`, docs/designs/deferred-queue-restore/).
 *
 * A signed-in phone whose server does not answer is asked what to do on the boot screen itself
 * (`bootUnreachable.js`: try again, wait for the server, or continue offline); after an offline
 * start, `watchServerReturn` keeps asking the server in the background and switches back once it
 * answers (docs/designs/app-start-reachability/).
 */
const app = platform.system.isNative
  ? bootstrapShell(platform, undefined, setBootStage, {
      decide: askServerDecision,
      deferQueue: true,
    }).then((result) => {
      // A fresh install has no server yet: the app opens on the first-run screen (issue #192).
      if (result?.needsServer) serverScreen.set("first");
      setBootStage("starting");
      watchServerReturn(platform, { onBack: announceServerBack });
      return mountApp();
    })
  : mountApp();

/**
 * Says that offline mode ended because the server answered again, and whether the full queue
 * came back with it (`reconcileQueue`: only when the listener had not started something else).
 *
 * @param {{restored: number}} outcome
 */
function announceServerBack(outcome) {
  const translate = get(t);
  notify.success(
    outcome?.restored > 0
      ? translate("offlineMode.backRestored", { count: outcome.restored })
      : translate("offlineMode.back"),
  );
}

/**
 * Mounts the app and takes the boot screen away once it has painted underneath
 * (`bootScreen.js`). A mount that throws still removes it: an error on the real page is
 * more use than a boot screen that never leaves.
 *
 * A page off the first screen (Management, settings, statistics...) lives in its own chunk
 * (`lazyViews.js`, issue #114). Opened by URL, that chunk is fetched first, behind the boot
 * screen, so the app appears with the page rather than with a skeleton in its place.
 * `preloadState` never rejects: a chunk that failed shows its retry pill once mounted. The
 * locale file is a chunk too and is waited for the same way (`localeReady`, never rejects).
 * Once the app is up, the pages one tap away are fetched on idle.
 */
async function mountApp() {
  await Promise.all([localeReady(), preloadState(initialState(window.location.pathname))]);
  try {
    return mount(App, { target });
  } finally {
    requestAnimationFrame(() => {
      dismissBootScreen();
      preloadLikelyNext();
    });
  }
}

export default app;
