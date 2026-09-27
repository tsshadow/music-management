import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { platform } from "./lib/platform/index.js";
import { bootstrapShell } from "./lib/nativeSession.js";
import { dismissBootScreen, setBootStage } from "./lib/bootScreen.js";
import { logError, identifyBundle } from "./lib/diagnosticsLog.js";

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

// Fire-and-forget: nothing here gates the first render, and a report is
// still useful without an answer -- see `identifyBundle`.
identifyBundle();

/**
 * In a browser the app mounts at once, and the boot screen leaves with the first frame.
 *
 * Inside the Android shell the app is mounted only after the phone's server,
 * session and playback queue have reached the stores -- the first component to
 * render otherwise fetches against `https://localhost`, which is the WebView
 * and not a music server. `bootstrapShell` never rejects, so a phone that
 * cannot reach its server still gets a login screen rather than a blank one.
 * Meanwhile the boot screen from index.html says which step it is on.
 */
const app = platform.system.isNative
  ? bootstrapShell(platform, undefined, setBootStage).then(() => {
      setBootStage("starting");
      return mountApp();
    })
  : mountApp();

/**
 * Mounts the app and takes the boot screen away once it has painted underneath
 * (`bootScreen.js`). A mount that throws still removes it: an error on the real page is
 * more use than a boot screen that never leaves.
 */
function mountApp() {
  try {
    return mount(App, { target });
  } finally {
    requestAnimationFrame(() => dismissBootScreen());
  }
}

export default app;
