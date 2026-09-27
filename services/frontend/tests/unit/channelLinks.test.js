import { describe, it, expect } from "vitest";
import {
  filterProposals,
  countByKind,
  kindLabel,
  sourceLabel,
  linksOf,
  refreshMessage,
  offersHandLink,
  firstUnlinkedKind,
  describeChannel,
  handLinkMessage,
} from "../../src/lib/management/channelLinks";

const ROWS = [
  {
    id: 1,
    platform: "soundcloud",
    kind: "label",
    channel_name: "TRAXTORM",
    target_name: "Traxtorm",
  },
  {
    id: 2,
    platform: "youtube",
    kind: "artist",
    channel_name: "D-Sturb",
    target_name: "D-Sturb",
  },
  {
    id: 3,
    platform: "soundcloud",
    kind: "artist",
    channel_name: "Monstercat",
    target_name: "Monstercat",
  },
];

describe("filterProposals", () => {
  it("keeps everything without a filter", () => {
    expect(filterProposals(ROWS).map((r) => r.id)).toEqual([1, 2, 3]);
  });

  it("filters on kind and platform together", () => {
    expect(
      filterProposals(ROWS, { kind: "artist", platform: "soundcloud" }).map((r) => r.id),
    ).toEqual([3]);
  });

  it("searches the channel and the proposed name, ignoring case", () => {
    expect(filterProposals(ROWS, { query: "sturb" }).map((r) => r.id)).toEqual([2]);
    expect(filterProposals(ROWS, { query: "traxTORM" }).map((r) => r.id)).toEqual([1]);
  });

  it("survives a missing list", () => {
    expect(filterProposals(null)).toEqual([]);
  });
});

describe("countByKind", () => {
  it("counts labels and artists", () => {
    expect(countByKind(ROWS)).toEqual({ label: 1, artist: 2 });
  });
});

describe("labels", () => {
  it("names the kind and the reason in Dutch", () => {
    expect(kindLabel("artist")).toBe("Artiest");
    expect(sourceLabel("redirect")).toBe("Doorverwijzing");
  });

  it("reports what a search did", () => {
    expect(refreshMessage({ created: 3, open: 10, withdrawn: 1, ambiguous: 2 })).toBe(
      "3 nieuwe voorstellen, 10 open, 1 vervallen, 2 kanalen overgeslagen als dubbelzinnig.",
    );
  });
});

describe("linksOf", () => {
  it("lists the label before the artist and skips what is not set", () => {
    expect(
      linksOf({
        label: { id: 1, name: "L" },
        artist: { id: 2, name: "A" },
      }).map((l) => l.kind),
    ).toEqual(["label", "artist"]);
    expect(linksOf({ label: null, artist: { id: 2, name: "A" } })).toEqual([
      { kind: "artist", id: 2, name: "A" },
    ]);
  });

  it("has nothing for an account without a channel", () => {
    expect(linksOf(null)).toEqual([]);
  });
});

describe("hand-linking helpers", () => {
  const unlinked = { id: 1, name: "Hysta Official", label: null, artist: null, open_proposals: 0 };

  it("offers a hand link for a channel with something unlinked and nothing to decide", () => {
    expect(offersHandLink(unlinked)).toBe(true);
    expect(offersHandLink({ ...unlinked, label: { id: 3, name: "X" } })).toBe(true);
    expect(offersHandLink({ ...unlinked, open_proposals: 2 })).toBe(false);
    expect(
      offersHandLink({ ...unlinked, label: { id: 3, name: "X" }, artist: { id: 4, name: "Y" } }),
    ).toBe(false);
    expect(offersHandLink(null)).toBe(false);
  });

  it("starts on the kind the channel lacks", () => {
    expect(firstUnlinkedKind(unlinked)).toBe("label");
    expect(firstUnlinkedKind({ ...unlinked, label: { id: 3, name: "X" } })).toBe("artist");
    expect(firstUnlinkedKind(null)).toBe("label");
  });

  it("describes a channel by platform, tracks and links, and skips what a coverage row lacks", () => {
    expect(
      describeChannel(
        {
          ...unlinked,
          platform: "youtube",
          track_count: 12,
          label: { id: 3, name: "Hysta Records" },
        },
        { youtube: "YouTube" },
      ),
    ).toBe("YouTube · 12 tracks · Label: Hysta Records");
    expect(describeChannel({ ...unlinked, artist: { id: 4, name: "Hysta" } })).toBe(
      "Artiest: Hysta",
    );
  });

  it("reports the link and how many files were queued", () => {
    expect(handLinkMessage({ target_name: "Hysta", queued: 44 }, "Hysta Official")).toBe(
      "Hysta Official gekoppeld aan Hysta; 44 bestanden staan klaar voor de tagger.",
    );
  });
});
