import { get } from "svelte/store";
import { t, localeReady } from "./i18n/index.js";
import { platform as defaultPlatform } from "./platform/index.js";
import { pauseBootHints } from "./bootScreen.js";
import { checkServer, isUnreachable, REACHABILITY, waitForServer } from "./serverReachability.js";

/**
 * The boot screen's "server unreachable" panel (docs/designs/app-start-reachability/, styleguide
 * "Boot screen: server unreachable").
 *
 * Shown in place of the stage line and the progress bar when the start-up check answered
 * `noNetwork` or `unreachable`. Three ways on:
 *
 * - **Opnieuw proberen** -- one more check, now.
 * - **Wachten op server** -- a calm waiting state: no queue restore yet, the check repeats with
 *   backoff (2 s, 5 s, 10 s, 20 s, then every 30 s) and at once when a network comes up; the panel
 *   says since when it waits and when the next attempt is. The normal start continues by itself
 *   the moment the server answers.
 * - **Offline verder** -- start with what is on the device. Available in both states.
 *
 * Built in script rather than in `index.html`: it only ever appears after the bundle runs, and
 * the styles it needs are the boot screen's own (the `boot-choice*` rules in `index.html`).
 */

/** How often the waiting state's countdown is redrawn. */
const TICK_MS = 1000;

/**
 * Shows the panel and resolves with the listener's decision.
 *
 * @param {{state: string}} first - The start-up check that failed.
 * @param {object} [options]
 * @param {object} [options.platform] - Injected by the tests.
 * @param {Document} [options.doc] - Injected by the tests.
 * @param {function(): Promise<{state: string}>} [options.check] - One attempt; injected by the tests.
 * @param {object} [options.timers] - `setTimeout`/`clearTimeout`/`setInterval`/`clearInterval`.
 * @param {function(): number} [options.now]
 * @returns {Promise<'online'|'offline'>} `online`: the server answered (or refused the
 *   credentials -- the login page handles that), continue the normal start.
 */
export async function askServerDecision(first, options = {}) {
  const {
    platform = defaultPlatform,
    doc = globalThis.document,
    check = () => checkServer(platform),
    timers = globalThis,
    now = Date.now,
  } = options;
  await localeReady();

  const screen = doc?.getElementById?.("boot-screen");
  // No boot screen to draw on (a second mount, a test without markup): start offline rather than
  // hang on a question nobody can see. The background watcher still brings the server back.
  if (!screen) return "offline";

  pauseBootHints(doc);
  const panel = buildPanel(doc);
  screen.appendChild(panel.root);
  screen.classList.add("boot-choosing");

  return await new Promise((resolve) => {
    let waiter = null;
    let ticker = null;
    let waitingSince = null;
    let nextAttemptAt = null;
    let checking = false;

    const text = (key, vars) => get(t)(key, vars);

    const done = (decision) => {
      waiter?.cancel();
      timers.clearInterval(ticker);
      panel.root.remove();
      screen.classList.remove("boot-choosing");
      resolve(decision);
    };

    const drawChoice = (state) => {
      const noNetwork = state === REACHABILITY.NO_NETWORK;
      panel.title.textContent = text(
        noNetwork ? "boot.reachability.noNetworkTitle" : "boot.reachability.unreachableTitle",
      );
      panel.body.textContent = text(
        noNetwork ? "boot.reachability.noNetworkBody" : "boot.reachability.unreachableBody",
      );
      panel.status.textContent = "";
      panel.wait.hidden = false;
      setBusy(false);
    };

    const drawWaiting = () => {
      panel.title.textContent = text("boot.reachability.waitingTitle");
      const since = new Date(waitingSince).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      panel.body.textContent = text("boot.reachability.waitingSince", { time: since });
      if (checking) {
        panel.status.textContent = text("boot.reachability.checking");
      } else if (nextAttemptAt !== null) {
        const seconds = Math.max(Math.ceil((nextAttemptAt - now()) / 1000), 0);
        panel.status.textContent = text("boot.reachability.nextAttempt", { seconds });
      }
      panel.wait.hidden = true;
    };

    const setBusy = (busy) => {
      checking = busy;
      panel.retry.disabled = busy;
      panel.wait.disabled = busy;
      if (busy && waiter === null) panel.status.textContent = text("boot.reachability.checking");
    };

    panel.retry.onclick = async () => {
      if (waiter) {
        waiter.retryNow();
        return;
      }
      setBusy(true);
      const result = await check();
      if (!isUnreachable(result?.state)) {
        done("online");
        return;
      }
      drawChoice(result.state);
    };

    panel.wait.onclick = () => {
      waitingSince = now();
      waiter = waitForServer({
        check,
        onConnectivity: (handler) => platform?.storage?.onConnectivity?.(handler) ?? (() => {}),
        onUpdate: (update) => {
          checking = update.checking === true;
          if (update.nextAttemptAt) nextAttemptAt = update.nextAttemptAt;
          drawWaiting();
        },
        timers,
        now,
      });
      waiter.promise.then((result) => {
        if (result) done("online");
      });
      ticker = timers.setInterval(drawWaiting, TICK_MS);
      drawWaiting();
    };

    panel.offline.onclick = () => done("offline");

    panel.retry.textContent = text("boot.reachability.retry");
    panel.wait.textContent = text("boot.reachability.wait");
    panel.offline.textContent = text("boot.reachability.continueOffline");
    drawChoice(first?.state);
  });
}

/**
 * The panel's elements. Plain DOM: the app is not mounted yet, and this has to look like the boot
 * screen it sits in rather than like the app.
 *
 * @param {Document} doc
 */
function buildPanel(doc) {
  const root = doc.createElement("div");
  root.className = "boot-choice";
  root.setAttribute("data-boot-choice", "");
  const title = doc.createElement("p");
  title.className = "boot-choice-title";
  const body = doc.createElement("p");
  body.className = "boot-choice-body";
  const status = doc.createElement("p");
  status.className = "boot-choice-status";
  const actions = doc.createElement("div");
  actions.className = "boot-choice-actions";
  const button = (action, primary) => {
    const element = doc.createElement("button");
    element.type = "button";
    element.className = primary ? "boot-pill boot-pill-primary" : "boot-pill";
    element.setAttribute("data-boot-action", action);
    actions.appendChild(element);
    return element;
  };
  const retry = button("retry", true);
  const wait = button("wait", false);
  const offline = button("offline", false);
  root.append(title, body, status, actions);
  return { root, title, body, status, retry, wait, offline };
}
