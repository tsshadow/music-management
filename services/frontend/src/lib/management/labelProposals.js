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
