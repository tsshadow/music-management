/**
 * Helpers for the label proposal tab.
 *
 * The importer leaves a release behind whenever it cannot place it, and proposes a
 * label read from the release's own tags. One label usually covers many releases, so
 * the list is grouped: confirming a group is one decision instead of fifteen.
 */

/**
 * Group proposals by their proposed label, the unlabelled ones last.
 *
 * Labelled groups are sorted by name so the list keeps the same order between loads —
 * a curator working down it should not have it reshuffle under them after every
 * confirmation. The proposals nothing could be read from go to the bottom: they are
 * the ones that need someone to actually go looking.
 */
export function groupByLabel(proposals) {
  const byLabel = new Map();
  for (const proposal of proposals) {
    const key = proposal.proposed_label ?? null;
    if (!byLabel.has(key)) byLabel.set(key, []);
    byLabel.get(key).push(proposal);
  }
  return [...byLabel.entries()]
    .map(([label, grouped]) => ({ label, proposals: grouped }))
    .sort((a, b) => {
      if (a.label === null) return 1;
      if (b.label === null) return -1;
      return a.label.localeCompare(b.label);
    });
}

/**
 * The reason codes the importer's extractor files a file under (bug report 119), mirrored
 * from services/importer/conflict_store.py. Anything else falls back to a generic line.
 */
export const IMPORT_FILE_REASONS = [
  "not-an-archive",
  "loose-audio",
  "not-music-video",
  "not-music-image",
  "not-music-document",
  "not-music-other",
  "unreadable",
  "extraction-failed",
  "extraction-empty",
  "extraction-name-taken",
];

/**
 * What one row of /api/import-conflicts is a problem about, as an i18n key under
 * `management.labelProposals` plus the detail to show beneath it.
 *
 * A folder pair from the renamer or mover has no reason: its problem is that the target
 * name is taken, and the detail is that target. A file from the extractor carries a
 * reason code, and its target is a detail (a backend error, say) or empty.
 */
export function describeImportConflict(conflict) {
  if (!conflict.reason) return { key: "conflictTaken", detail: conflict.target };
  const reason = IMPORT_FILE_REASONS.includes(conflict.reason) ? conflict.reason : "unknown";
  return { key: `conflictReasons.${reason}`, detail: conflict.target || "" };
}
