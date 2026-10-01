import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";

import BpmOverride from "../../src/lib/BpmOverride.svelte";
import TrackInspector from "../../src/lib/management/library/TrackInspector.svelte";
import {
  clearManualBpm,
  overrideErrorDetail,
  overrideFields,
  setManualBpm,
} from "../../src/lib/bpm.js";
import { MumaHttpError } from "../../src/lib/mumaApi.js";
import { mumaApiKey, mumaApiUrl, mumaUser, userPermissions } from "../../src/lib/store.js";
import { tagRows } from "../../src/lib/trackFile.js";

/**
 * The hand correction of a track's tempo: the two requests, and the control that sends them from
 * the management library's inspector (and the player's details sheet, which reuses it).
 */

/** An override answer as MuMa sends it. */
function answer(extra = {}) {
  return {
    track_id: 42,
    bpm: 87.5,
    bpm_source: "manual",
    bpm_confidence: "high",
    bpm_folded: false,
    bpm_approximate: false,
    measured_bpm: 175,
    raw_bpm: 175,
    ...extra,
  };
}

/** A fetch answering every call with `status` and `body`. */
function answering(status, body) {
  return vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  }));
}

const TRACK = {
  id: 42,
  title: "Raise Your Fist",
  artist: "Angerfist",
  bpm: 175,
  bpm_source: "measured",
  bpm_approximate: false,
};

beforeEach(() => {
  mumaApiUrl.set("http://muma");
  mumaApiKey.set("key");
  mumaUser.set(null);
  userPermissions.set(["bpm.override"]);
});

afterEach(() => {
  userPermissions.set([]);
  vi.restoreAllMocks();
});

describe("bpm override requests", () => {
  it("halves the tempo with a PUT carrying the factor", async () => {
    globalThis.fetch = answering(200, answer());

    await expect(setManualBpm(42, { factor: 0.5 })).resolves.toEqual(answer());

    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe("http://muma/api/library/bpm/tracks/42/manual");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(options.body)).toEqual({ factor: 0.5 });
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(options.headers["X-API-Key"]).toBe("key");
  });

  it("goes back to the measured tempo with a DELETE", async () => {
    globalThis.fetch = answering(200, answer({ bpm: 175, bpm_source: "measured" }));

    await clearManualBpm(42);

    const [url, options] = globalThis.fetch.mock.calls[0];
    expect(url).toBe("http://muma/api/library/bpm/tracks/42/manual");
    expect(options.method).toBe("DELETE");
  });

  it("reads the server's detail from a refusal, and nothing from anything else", () => {
    expect(overrideErrorDetail(new MumaHttpError(409, { detail: "No BPM to halve" }))).toBe(
      "No BPM to halve",
    );
    expect(overrideErrorDetail(new MumaHttpError(422, { detail: [{ msg: "bad" }] }))).toBeNull();
    expect(overrideErrorDetail(new Error("offline"))).toBeNull();
  });

  it("keeps only the BPM fields of an answer", () => {
    expect(overrideFields(answer({ bpm_approximate: 1 }))).toEqual({
      bpm: 87.5,
      bpm_source: "manual",
      bpm_confidence: "high",
      bpm_folded: false,
      bpm_approximate: true,
    });
    expect(overrideFields(null).bpm).toBeNull();
  });
});

describe("BpmOverride", () => {
  it("shows nothing to a user without the bpm.override permission", () => {
    userPermissions.set([]);
    render(BpmOverride, { trackId: 42, bpm: 175, source: "measured" });

    expect(screen.queryByTestId("bpm-override")).toBeNull();
  });

  it("shows the controls to an admin even without the permission itself", () => {
    userPermissions.set([]);
    mumaUser.set({ is_admin: true });
    render(BpmOverride, { trackId: 42, bpm: 175, source: "measured" });

    expect(screen.getByTestId("bpm-override")).toBeTruthy();
  });

  it("shows nothing without a library track id", () => {
    render(BpmOverride, { trackId: null, bpm: 175 });

    expect(screen.queryByTestId("bpm-override")).toBeNull();
  });

  it("sends factor 2 for 2× and hands the answer to onchange", async () => {
    globalThis.fetch = answering(200, answer({ bpm: 350 }));
    const onchange = vi.fn();
    render(BpmOverride, { trackId: 42, bpm: 175, source: "measured", onchange });

    await fireEvent.click(screen.getByLabelText("Tempo verdubbelen"));

    await waitFor(() => expect(onchange).toHaveBeenCalled());
    expect(JSON.parse(globalThis.fetch.mock.calls[0][1].body)).toEqual({ factor: 2 });
    expect(onchange.mock.calls[0][0]).toMatchObject({ bpm: 350, bpm_source: "manual" });
  });

  it("offers no halving or doubling when there is no tempo to scale", () => {
    render(BpmOverride, { trackId: 42, bpm: null, source: null });

    expect(screen.getByLabelText("Tempo halveren").disabled).toBe(true);
    expect(screen.getByLabelText("Tempo verdubbelen").disabled).toBe(true);
    expect(screen.queryByText("Gemeten")).toBeNull();
  });

  it("refuses a typed tempo outside 40-500 without asking MuMa", async () => {
    globalThis.fetch = vi.fn();
    render(BpmOverride, { trackId: 42, bpm: 175, source: "measured" });

    await fireEvent.input(screen.getByLabelText("Tempo in BPM"), { target: { value: "12" } });
    await fireEvent.click(screen.getByText("Zet"));

    expect(screen.getByTestId("bpm-override-error").textContent).toBe(
      "Vul een tempo tussen 40 en 500 in.",
    );
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("falls back to its own message when MuMa sent no detail", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    render(BpmOverride, { trackId: 42, bpm: 175, source: "measured" });

    await fireEvent.click(screen.getByLabelText("Tempo halveren"));

    await waitFor(() =>
      expect(screen.getByTestId("bpm-override-error").textContent).toBe(
        "Het tempo kon niet worden aangepast.",
      ),
    );
  });

  it("disables its buttons while a request is in flight", async () => {
    let release;
    globalThis.fetch = vi.fn(
      () =>
        new Promise((resolve) => {
          release = () => resolve({ ok: true, status: 200, json: async () => answer() });
        }),
    );
    render(BpmOverride, { trackId: 42, bpm: 175, source: "manual" });

    await fireEvent.click(screen.getByLabelText("Tempo halveren"));

    await waitFor(() => expect(screen.getByLabelText("Tempo verdubbelen").disabled).toBe(true));
    expect(screen.getByText("Gemeten").disabled).toBe(true);
    expect(screen.getByText("Zet").disabled).toBe(true);
    release();
    await waitFor(() => expect(screen.getByLabelText("Tempo verdubbelen").disabled).toBe(false));
  });
});

describe("TrackInspector tempo correction", () => {
  /** Renders the inspector with the handlers it needs. */
  function renderInspector(track = TRACK, extra = {}) {
    return render(TrackInspector, {
      track,
      onRerunParse: vi.fn(),
      onRedownload: vi.fn(),
      ...extra,
    });
  }

  it("hides the controls without the permission", () => {
    userPermissions.set([]);
    renderInspector();

    expect(screen.queryByText("Tempo halveren")).toBeNull();
    expect(screen.queryByTestId("bpm-override")).toBeNull();
    expect(screen.getByText("175")).toBeTruthy();
  });

  it("sends factor 0.5 for ½× and shows the answer, marked manual", async () => {
    globalThis.fetch = answering(200, answer());
    const onBpmChange = vi.fn();
    renderInspector(TRACK, { onBpmChange });

    expect(screen.queryByTestId("bpm-manual-marker")).toBeNull();
    await fireEvent.click(screen.getByLabelText("Tempo halveren"));

    await waitFor(() => expect(screen.getByText("88")).toBeTruthy());
    expect(JSON.parse(globalThis.fetch.mock.calls[0][1].body)).toEqual({ factor: 0.5 });
    expect(screen.getByTestId("bpm-manual-marker").textContent).toBe("handmatig");
    expect(onBpmChange).toHaveBeenCalledWith(
      expect.objectContaining({ id: 42, bpm: 87.5, bpm_source: "manual" }),
      expect.objectContaining({ bpm: 87.5 }),
    );
  });

  it("sets a typed tempo", async () => {
    globalThis.fetch = answering(200, answer({ bpm: 150 }));
    renderInspector();

    await fireEvent.input(screen.getByLabelText("Tempo in BPM"), { target: { value: "150" } });
    await fireEvent.click(screen.getByText("Zet"));

    await waitFor(() => expect(screen.getByText("150")).toBeTruthy());
    expect(JSON.parse(globalThis.fetch.mock.calls[0][1].body)).toEqual({ bpm: 150 });
  });

  it("offers Measured only for a manual tempo, and sends a DELETE for it", async () => {
    globalThis.fetch = answering(200, answer({ bpm: 175, bpm_source: "measured" }));
    renderInspector({ ...TRACK, bpm: 87.5, bpm_source: "manual" });

    expect(screen.getByTestId("bpm-manual-marker")).toBeTruthy();
    await fireEvent.click(screen.getByText("Gemeten"));

    await waitFor(() => expect(screen.getByText("175")).toBeTruthy());
    expect(globalThis.fetch.mock.calls[0][1].method).toBe("DELETE");
    expect(screen.queryByTestId("bpm-manual-marker")).toBeNull();
    expect(screen.queryByText("Gemeten")).toBeNull();
  });

  it("shows the server's refusal inline", async () => {
    globalThis.fetch = answering(409, { detail: "Track 42 has no BPM to scale" });
    renderInspector();

    await fireEvent.click(screen.getByLabelText("Tempo verdubbelen"));

    await waitFor(() =>
      expect(screen.getByTestId("bpm-override-error").textContent).toBe(
        "Track 42 has no BPM to scale",
      ),
    );
    expect(screen.getByText("175")).toBeTruthy();
  });
});

describe("tagRows manual marker", () => {
  it("flags a tempo set by hand, and only that", () => {
    expect(tagRows({ bpm: 150, bpm_source: "manual" }, {})).toEqual([
      { key: "bpm", value: "150", manual: true },
    ]);
    expect(tagRows({ bpm: 150, bpm_source: "measured" }, {})).toEqual([
      { key: "bpm", value: "150" },
    ]);
  });
});
