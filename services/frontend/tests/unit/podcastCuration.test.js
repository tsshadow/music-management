import { describe, it, expect } from 'vitest';
import {
  WHITE,
  BLACK,
  UNKNOWN,
  buildAlias,
  buildDecision,
  buildRename,
  describeEpisodes,
  describeOutcome,
  extraAliases,
  filterPodcasts,
  mergeTargets,
  summarize
} from '../../src/lib/management/podcastCuration';

const row = (over = {}) => ({
  id: 1,
  name: "Isaac's Hardstyle Sessions",
  state: UNKNOWN,
  aliases: [],
  occurrences: 0,
  ...over
});

describe('filterPodcasts', () => {
  it('returns everything for an empty query', () => {
    const rows = [row(), row({ id: 2, name: 'Euphoricast' })];
    expect(filterPodcasts(rows, '')).toEqual(rows);
  });

  it('ignores case and punctuation', () => {
    expect(filterPodcasts([row()], 'HARDSTYLE Sessions!')).toHaveLength(1);
  });

  it('ignores accents', () => {
    expect(filterPodcasts([row({ name: 'Euphoricast' })], 'euphóricast')).toHaveLength(1);
  });

  it('matches a spelling that is not the shows own name', () => {
    const rows = [row({ aliases: ['DJ ISAAC - HARDSTYLE SESSIONS'] })];
    expect(filterPodcasts(rows, 'dj isaac')).toHaveLength(1);
  });

  it('drops rows that match neither name nor spelling', () => {
    expect(filterPodcasts([row()], 'defqon')).toEqual([]);
  });
});

describe('describeOutcome', () => {
  it('says an approved show is tagged', () => {
    expect(describeOutcome(row({ state: WHITE }))).toMatch(/getagd/);
  });

  it('says a rejected show is never tagged', () => {
    expect(describeOutcome(row({ state: BLACK }))).toMatch(/nooit/);
  });

  it('spells out that undecided means unlabelled', () => {
    expect(describeOutcome(row())).toMatch(/niet getagd/);
  });
});

describe('extraAliases', () => {
  it('leaves out the spelling that equals the name', () => {
    const subject = row({ aliases: ["Isaac's Hardstyle Sessions", 'Hardstyle Sessions'] });
    expect(extraAliases(subject)).toEqual(['Hardstyle Sessions']);
  });

  it('handles a row with no aliases at all', () => {
    expect(extraAliases(row())).toEqual([]);
  });
});

describe('buildDecision', () => {
  it('rejects a state that is not white or black', () => {
    expect(buildDecision({ podcastId: 1, state: UNKNOWN }).valid).toBe(false);
  });

  it('builds a plain approval', () => {
    expect(buildDecision({ podcastId: 1, state: WHITE }).payload).toEqual({
      state: WHITE,
      host: null,
      station: null
    });
  });

  it('passes the host and station through', () => {
    const decision = buildDecision({ podcastId: 1, state: WHITE, host: 'DJ Isaac', station: 'Q-dance' });
    expect(decision.payload).toEqual({ state: WHITE, host: 'DJ Isaac', station: 'Q-dance' });
  });

  it('builds a merge and drops the descriptive fields', () => {
    const decision = buildDecision({ podcastId: 1, state: WHITE, mergeIntoId: '9' });
    expect(decision.payload).toEqual({ state: WHITE, merge_into_podcast_id: 9 });
  });

  it('refuses a merge into itself', () => {
    const decision = buildDecision({ podcastId: 1, state: WHITE, mergeIntoId: 1 });
    expect(decision.valid).toBe(false);
    expect(decision.error).toMatch(/zichzelf/);
  });

  it('treats an empty merge target as no merge', () => {
    expect(buildDecision({ podcastId: 1, state: BLACK, mergeIntoId: '' }).payload).toEqual({
      state: BLACK,
      host: null,
      station: null
    });
  });
});

describe('mergeTargets', () => {
  const rows = [
    row({ id: 1, name: 'DJ ISAAC - HARDSTYLE SESSIONS', state: UNKNOWN }),
    row({ id: 2, name: "Isaac's Hardstyle Sessions", state: WHITE }),
    row({ id: 3, name: 'Euphoricast', state: WHITE }),
    row({ id: 4, name: 'B2S TV', state: BLACK })
  ];

  it('offers only approved shows', () => {
    expect(mergeTargets(rows, 1).map((r) => r.id)).toEqual([3, 2]);
  });

  it('never offers the row itself', () => {
    expect(mergeTargets(rows, 2).map((r) => r.id)).toEqual([3]);
  });
});

describe('summarize', () => {
  it('counts the states for the header badges', () => {
    const rows = [row({ state: WHITE }), row({ state: BLACK }), row(), row()];
    expect(summarize(rows)).toEqual({ white: 1, black: 1, unknown: 2, total: 4 });
  });
});

describe('describeEpisodes', () => {
  it('uses the singular for one episode', () => {
    expect(describeEpisodes(row({ occurrences: 1 }))).toBe('1 aflevering');
  });

  it('uses the plural otherwise', () => {
    expect(describeEpisodes(row({ occurrences: 125 }))).toBe('125 afleveringen');
  });

  it('treats a missing count as zero', () => {
    expect(describeEpisodes(row({ occurrences: null }))).toBe('0 afleveringen');
  });
});

describe('buildRename', () => {
  it('accepts a real show name and trims it', () => {
    expect(buildRename('  Pure Hardstyle ')).toEqual({
      valid: true,
      error: null,
      payload: { name: 'Pure Hardstyle' }
    });
  });

  it('refuses an empty name', () => {
    expect(buildRename('   ').valid).toBe(false);
  });

  it('refuses a name with nothing to match on', () => {
    // Punctuation normalizes away, so this is as empty as a blank one.
    expect(buildRename(' - | - ').valid).toBe(false);
  });

  it('refuses a name too short to be a safe matcher', () => {
    const built = buildRename('Q!');
    expect(built.valid).toBe(false);
    expect(built.error).toContain('4');
  });
});

describe('buildAlias', () => {
  it('accepts a spelling and trims it', () => {
    expect(buildAlias(' KELTEK | Pure Hardstyle | ')).toEqual({
      valid: true,
      error: null,
      payload: { alias: 'KELTEK | Pure Hardstyle |' }
    });
  });

  it('refuses an empty spelling', () => {
    expect(buildAlias('').valid).toBe(false);
  });

  it('refuses a spelling too short to be a safe matcher', () => {
    const built = buildAlias('HS');
    expect(built.valid).toBe(false);
    expect(built.error).toContain('4');
  });
});
