/**
 * Helpers for the downloader Links tab and the "Gekoppeld aan" column.
 *
 * The API proposes a label or artist per channel where the names leave no doubt
 * (docs/designs/channel-links). Filtering happens here, on the client: a
 * thousand proposals is a list, not a dataset.
 */

import { get } from "svelte/store";
import { t } from "../i18n/index.js";

export const KINDS = ["label", "artist"];
export const PLATFORMS = ["soundcloud", "youtube"];

/**
 * Keep the proposals the chosen kind, platform and search term ask for.
 * An empty kind or platform means "all"; the search matches channel and target.
 */
export function filterProposals(rows, { kind = "", platform = "", query = "" } = {}) {
  const needle = (query || "").trim().toLowerCase();
  return (rows || []).filter((row) => {
    if (kind && row.kind !== kind) return false;
    if (platform && row.platform !== platform) return false;
    if (!needle) return true;
    return [row.channel_name, row.target_name].some((value) =>
      String(value || "")
        .toLowerCase()
        .includes(needle),
    );
  });
}

/** How many proposals of each kind a list holds, for the filter's counts. */
export function countByKind(rows) {
  const counts = { label: 0, artist: 0 };
  for (const row of rows || []) {
    if (row.kind in counts) counts[row.kind] += 1;
  }
  return counts;
}

/** "label" / "artist" in the current language. */
export function kindLabel(kind) {
  return get(t)(`management.downloaders.links.kind.${kind}`);
}

/** Why a proposal was made: the name itself, an alias, or a curator's redirect. */
export function sourceLabel(source) {
  return get(t)(`management.downloaders.links.source.${source}`);
}

/**
 * The links a coverage row's channel carries, as `{kind, id, name}` entries in a
 * fixed order (label first). An account without a channel has none.
 */
export function linksOf(channel) {
  if (!channel) return [];
  return KINDS.filter((kind) => channel[kind]).map((kind) => ({
    kind,
    ...channel[kind],
  }));
}

/** The message the tab shows after a search, from its counts. */
export function refreshMessage(result) {
  return get(t)("management.downloaders.links.refreshed", {
    created: result?.created ?? 0,
    open: result?.open ?? 0,
    withdrawn: result?.withdrawn ?? 0,
    ambiguous: result?.ambiguous ?? 0,
  });
}

/**
 * Whether the Coverage table offers "koppelen" for a channel: it has a
 * channel, no open proposal to decide instead, and at least one kind unlinked.
 */
export function offersHandLink(channel) {
  if (!channel || channel.open_proposals) return false;
  return KINDS.some((kind) => !channel[kind]);
}

/** The kind a hand link should start on: the first one the channel lacks. */
export function firstUnlinkedKind(channel) {
  return KINDS.find((kind) => !channel?.[kind]) ?? KINDS[0];
}

/** The muted line under a channel suggestion: platform, tracks, current links. */
export function describeChannel(channel, platformLabels = {}) {
  if (!channel) return "";
  const parts = [];
  if (channel.platform) parts.push(platformLabels[channel.platform] ?? channel.platform);
  if (channel.track_count != null) {
    parts.push(
      get(t)("management.downloaders.links.byHand.tracks", {
        count: channel.track_count,
      }),
    );
  }
  for (const link of linksOf(channel)) parts.push(`${kindLabel(link.kind)}: ${link.name}`);
  return parts.join(" · ");
}

/** The message after a hand link, from the PUT response. */
export function handLinkMessage(result, channelName) {
  return get(t)("management.downloaders.links.byHand.linked", {
    channel: channelName,
    target: result?.target_name ?? "",
    queued: result?.queued ?? 0,
  });
}
