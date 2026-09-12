import { registerPlugin } from "@capacitor/core";
import { createCapacitorPlayer } from "./player.js";
import { createCapacitorStorage } from "./storage.js";
import { createCapacitorSpeech } from "./speech.js";
import { createCapacitorDiagnostics } from "./diagnostics.js";
import { createCapacitorSystem } from "./system.js";

/**
 * The platform implementation for the Android shell.
 *
 * Every member is a thin proxy over one Kotlin plugin; nothing here decides
 * anything. The names must match the `@CapacitorPlugin(name = ...)` annotations
 * in `services/muma-mobile/.../capacitor/`, because that string is the whole of
 * the binding -- a typo produces a plugin object whose every call rejects with
 * "not implemented", which reads as a broken feature rather than a broken name.
 *
 * Built through a function rather than at import time so that a browser tab,
 * which imports this module as part of the platform selection, never registers
 * a plugin it cannot reach.
 *
 * @param {function(string): object} [register] - Injected by the tests.
 * @returns {import('../index.js').Platform}
 */
export function createCapacitorPlatform(register = registerPlugin) {
  return {
    player: createCapacitorPlayer(register("MumaPlayer")),
    storage: createCapacitorStorage(register("MumaStorage")),
    speech: createCapacitorSpeech(register("MumaSpeech")),
    diagnostics: createCapacitorDiagnostics(register("MumaDiagnostics")),
    system: createCapacitorSystem(register("MumaSystem")),
  };
}
