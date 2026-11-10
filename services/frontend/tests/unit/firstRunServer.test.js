import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/svelte";
import FirstRunServer from "../../src/lib/FirstRunServer.svelte";

/**
 * The first-run server screen (issue #192, docs/designs/first-run-server/): what it shows for
 * each answer of the phone's check, and when it hands the address on.
 */
function fakePlatform({ check = { state: "ok" }, suggestion = "" } = {}) {
  return {
    system: {
      isNative: true,
      suggestedServerAddress: vi.fn(async () => suggestion),
      checkServerAddress: vi.fn(async (url) =>
        typeof check === "function"
          ? check(url)
          : {
              url: "https://music.example.net",
              subsonic: "",
              mumaApi: "",
              buildServer: false,
              ...check,
            },
      ),
    },
  };
}

function field(getByLabelText) {
  return getByLabelText("Serveradres");
}

describe("FirstRunServer", () => {
  it("prefills the build's server on a first run and shows the example", async () => {
    const platform = fakePlatform({ suggestion: "https://music.example.org" });
    const { getByLabelText, getByText } = render(FirstRunServer, { platform, onconfirm: vi.fn() });

    await waitFor(() => expect(field(getByLabelText).value).toBe("https://music.example.org"));
    expect(getByText("https://music.example.net")).toBeInTheDocument();
    expect(getByText("Met welke server wil je verbinden?")).toBeInTheDocument();
  });

  it("starts from the current address when it changes the server, and can be cancelled", async () => {
    const platform = fakePlatform({ suggestion: "https://ignored.example" });
    const oncancel = vi.fn();
    const { getByLabelText, getByText } = render(FirstRunServer, {
      platform,
      mode: "change",
      current: "https://music.example.org",
      onconfirm: vi.fn(),
      oncancel,
    });

    await waitFor(() => expect(field(getByLabelText).value).toBe("https://music.example.org"));
    expect(getByText("Andere server")).toBeInTheDocument();
    await fireEvent.click(getByText("Annuleren"));
    expect(oncancel).toHaveBeenCalledOnce();
  });

  it("hands a server that checks out on at once", async () => {
    const platform = fakePlatform();
    const onconfirm = vi.fn(async () => {});
    const { getByLabelText, getByText } = render(FirstRunServer, { platform, onconfirm });

    await fireEvent.input(field(getByLabelText), { target: { value: " music.example.net " } });
    await fireEvent.click(getByText("Verbinden"));

    await waitFor(() => expect(onconfirm).toHaveBeenCalledOnce());
    expect(platform.system.checkServerAddress).toHaveBeenCalledWith("music.example.net");
    expect(onconfirm.mock.calls[0][0]).toMatchObject({
      state: "ok",
      url: "https://music.example.net",
    });
  });

  it.each([
    ["invalid", "Dit is geen serveradres."],
    ["insecure", "Alleen https-adressen werken, ook op je thuisnetwerk."],
    ["notMuma", "Op dit adres is geen MuMa-server gevonden."],
    [
      "certificate",
      "De verbinding is niet veilig: het certificaat van deze server wordt niet vertrouwd.",
    ],
    ["unreachable", "De server op https://music.example.net antwoordt niet."],
  ])("stays on %s and says why", async (state, text) => {
    const platform = fakePlatform({ check: { state } });
    const onconfirm = vi.fn();
    const { getByLabelText, getByText, findByRole, queryByText } = render(FirstRunServer, {
      platform,
      onconfirm,
    });

    await fireEvent.input(field(getByLabelText), { target: { value: "music.example.net" } });
    await fireEvent.click(getByText("Verbinden"));

    expect((await findByRole("alert")).textContent).toBe(text);
    expect(onconfirm).not.toHaveBeenCalled();
    expect(queryByText("Toch doorgaan")).toBeNull();
  });

  it("offers to go on anyway when only MuMa does not answer", async () => {
    const platform = fakePlatform({ check: { state: "mumaUnreachable" } });
    const onconfirm = vi.fn(async () => {});
    const { getByLabelText, getByText, findByText } = render(FirstRunServer, {
      platform,
      onconfirm,
    });

    await fireEvent.input(field(getByLabelText), { target: { value: "music.example.net" } });
    await fireEvent.click(getByText("Verbinden"));
    await fireEvent.click(await findByText("Toch doorgaan"));

    await waitFor(() => expect(onconfirm).toHaveBeenCalledOnce());
    expect(onconfirm.mock.calls[0][0].state).toBe("mumaUnreachable");
  });

  it("checks again from the no-network message", async () => {
    let answers = 0;
    const platform = fakePlatform({
      check: () =>
        answers++ === 0
          ? { state: "noNetwork", url: "https://music.example.net" }
          : { state: "ok", url: "https://music.example.net" },
    });
    const onconfirm = vi.fn(async () => {});
    const { getByLabelText, getByText, findByText } = render(FirstRunServer, {
      platform,
      onconfirm,
    });

    await fireEvent.input(field(getByLabelText), { target: { value: "music.example.net" } });
    await fireEvent.click(getByText("Verbinden"));
    await fireEvent.click(await findByText("Opnieuw proberen"));

    await waitFor(() => expect(onconfirm).toHaveBeenCalledOnce());
    expect(platform.system.checkServerAddress).toHaveBeenCalledTimes(2);
  });

  it("disables the field while it checks", async () => {
    let finish;
    const platform = fakePlatform({
      check: () =>
        new Promise((resolve) => (finish = () => resolve({ state: "notMuma", url: "" }))),
    });
    const { getByLabelText, getByText, findByText } = render(FirstRunServer, {
      platform,
      onconfirm: vi.fn(),
    });

    await fireEvent.input(field(getByLabelText), { target: { value: "music.example.net" } });
    await fireEvent.click(getByText("Verbinden"));

    expect(await findByText("Server controleren…")).toBeInTheDocument();
    expect(field(getByLabelText)).toBeDisabled();
    finish();
    await waitFor(() => expect(field(getByLabelText)).not.toBeDisabled());
  });

  it("reads a check that could not run as no answer", async () => {
    const platform = fakePlatform();
    platform.system.checkServerAddress = vi.fn(async () => {
      throw new Error("bridge gone");
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    const { getByLabelText, getByText, findByRole } = render(FirstRunServer, {
      platform,
      onconfirm: vi.fn(),
    });

    await fireEvent.input(field(getByLabelText), { target: { value: "music.example.net" } });
    await fireEvent.click(getByText("Verbinden"));

    expect((await findByRole("alert")).textContent).toBe(
      "De server op music.example.net antwoordt niet.",
    );
  });

  it("shows a failure to store and stays", async () => {
    const platform = fakePlatform();
    const onconfirm = vi.fn(async () => {
      throw Object.assign(new Error("insecure"), { code: "insecure" });
    });
    const { getByLabelText, getByText, findByRole } = render(FirstRunServer, {
      platform,
      onconfirm,
    });

    await fireEvent.input(field(getByLabelText), { target: { value: "music.example.net" } });
    await fireEvent.click(getByText("Verbinden"));

    expect((await findByRole("alert")).textContent).toBe(
      "Het adres kon niet worden opgeslagen: insecure",
    );
  });
});
