import { mount } from "svelte";
import "./app.css";
import App from "./App.svelte";
import { platform } from "./lib/platform/index.js";
import { bootstrapShell } from "./lib/nativeSession.js";

const target = document.querySelector("#app");

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
