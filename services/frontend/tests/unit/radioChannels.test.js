import { describe, it, expect } from 'vitest';
import {
  emptyFilterForm,
  filterToForm,
  formToFilter,
  describeFilter,
  slugify,
  chooseChannel
} from '../../src/lib/management/radioChannels';

describe('formToFilter', () => {
  it('drops blank fields so an untouched form means the whole library', () => {
    expect(formToFilter(emptyFilterForm())).toEqual({});
  });

  it('keeps what was filled in, trimmed', () => {
    const form = { ...emptyFilterForm(), label: '  Q-dance Records  ', length: 'short' };
    expect(formToFilter(form)).toEqual({ label: 'Q-dance Records', length: 'short' });
  });

  it('sends numbers as numbers', () => {
    const form = { ...emptyFilterForm(), rating_min: '4', duration_max: '300' };
    expect(formToFilter(form)).toEqual({ rating_min: 4, duration_max: 300 });
  });

  it('ignores a number field that is not a number', () => {
    const form = { ...emptyFilterForm(), rating_min: 'four' };
    expect(formToFilter(form)).toEqual({});
  });

  it('only carries include_unrated alongside a rating bound', () => {
    expect(formToFilter({ ...emptyFilterForm(), include_unrated: true })).toEqual({});
    expect(formToFilter({ ...emptyFilterForm(), include_unrated: true, rating_min: '4' }))
      .toEqual({ rating_min: 4, include_unrated: true });
  });
});

describe('filterToForm', () => {
  it('round-trips a stored filter', () => {
    const stored = { label: 'Dirty Workz', rating_min: 4, include_unrated: true };
    expect(formToFilter(filterToForm(stored))).toEqual(stored);
  });

  it('starts empty for a channel without a filter', () => {
    expect(filterToForm(null)).toEqual(emptyFilterForm());
  });
});

describe('describeFilter', () => {
  it('says what an empty filter is, in the caller/s words', () => {
    expect(describeFilter({}, 'Whole library')).toBe('Whole library');
  });

  it('joins the named parts', () => {
    expect(describeFilter({ label: 'Q-dance Records', genre: 'hardstyle' }))
      .toBe('Q-dance Records · hardstyle');
  });

  it('renders a duration range as minutes and seconds', () => {
    expect(describeFilter({ duration_min: 90, duration_max: 300 })).toBe('1:30–5:00');
    expect(describeFilter({ duration_max: 300 })).toBe('≤ 5:00');
    expect(describeFilter({ duration_min: 240 })).toBe('≥ 4:00');
  });

  it('reads a rating floor as "and up", and the top rating as itself', () => {
    expect(describeFilter({ rating_min: 4 })).toBe('4★+');
    expect(describeFilter({ rating_min: 5 })).toBe('5★');
  });
});

describe('slugify', () => {
  it('makes a url-safe slug out of a channel name', () => {
    expect(slugify('Q-dance Records')).toBe('q-dance-records');
  });

  it('strips accents and punctuation rather than encoding them', () => {
    expect(slugify('Café Déjà-vu!')).toBe('cafe-deja-vu');
  });

  it('is empty for a name with nothing usable in it', () => {
    expect(slugify('!!!')).toBe('');
  });
});

describe('chooseChannel', () => {
  const channels = [{ slug: 'main' }, { slug: 'qdance' }];

  it('prefers the channel asked for', () => {
    expect(chooseChannel(channels, 'qdance').slug).toBe('qdance');
  });

  it('falls back to the first when the preferred one is gone', () => {
    expect(chooseChannel(channels, 'deleted').slug).toBe('main');
  });

  it('returns null when there is nothing to tune into', () => {
    expect(chooseChannel([], 'main')).toBeNull();
  });
});
