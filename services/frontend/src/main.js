import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { platform } from "./lib/platform/index.js";
import { bootstrapShell } from "./lib/nativeSession.js";
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
 * In a browser this is the same single line it has always been.
 *
 * Inside the Android shell the app is mounted only after the phone's server,
 * session and playback queue have reached the stores -- the first component to
 * render otherwise fetches against `https://localhost`, which is the WebView
 * and not a music server. `bootstrapShell` never rejects, so a phone that
 * cannot reach its server still gets a login screen rather than a blank one.
 */
const app = platform.system.isNative
  ? bootstrapShell().then(() => mount(App, { target }))
  : mount(App, { target });

export default app;
