import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  isSupported,
  attach,
  setEnabled,
  setBand,
  setGains,
  setPreamp,
  resume,
  __setContextFactoryForTests,
  __resetForTests,
} from '../../src/lib/equalizer.js';
import { EQ_FREQUENCIES, EQ_Q } from '../../src/lib/equalizerPresets.js';

/**
 * jsdom ships no Web Audio API, so the tests drive a stand-in that records
 * everything the module builds and connects.
 */
function makeFakeContext(overrides = {}) {
  const nodes = [];
  const make = (kind) => {
    const node = {
      kind,
      connectedTo: [],
      connect(target) { this.connectedTo.push(target); },
      disconnect() { this.connectedTo = []; },
    };
    nodes.push(node);
    return node;
  };
  const context = {
    state: 'running',
    destination: { kind: 'destination', connectedTo: [], connect() {} },
    nodes,
    resume: vi.fn(function () { this.state = 'running'; }),
    createMediaElementSource: vi.fn(() => make('source')),
    createGain: vi.fn(() => Object.assign(make('gain'), { gain: { value: 1 } })),
    createBiquadFilter: vi.fn(() => Object.assign(make('filter'), {
      type: '',
      frequency: { value: 0 },
      Q: { value: 0 },
      gain: { value: 0 },
    })),
    ...overrides,
  };
  return context;
}

const audioElement = {};

function filtersOf(context) {
  return context.nodes.filter((n) => n.kind === 'filter');
}

function preampOf(context) {
  return context.nodes.find((n) => n.kind === 'gain');
}

describe('equalizer audio graph', () => {
  let context;

  beforeEach(() => {
    __resetForTests();
    context = makeFakeContext();
    __setContextFactoryForTests(() => context);
  });

  it('reports support when a context can be built', () => {
    expect(isSupported()).toBe(true);
  });

  it('builds one peaking filter per band, at the documented frequencies', () => {
    expect(attach(audioElement)).toBe(true);

    const filters = filtersOf(context);
    expect(filters).toHaveLength(EQ_FREQUENCIES.length);
    filters.forEach((filter, i) => {
      expect(filter.type).toBe('peaking');
      expect(filter.frequency.value).toBe(EQ_FREQUENCIES[i]);
      expect(filter.Q.value).toBe(EQ_Q);
    });
  });

  it('chains source into preamp, through every band, and out to the destination', () => {
    attach(audioElement);

    const source = context.nodes.find((n) => n.kind === 'source');
    const preamp = preampOf(context);
    const filters = filtersOf(context);

    expect(source.connectedTo).toEqual([preamp]);
    expect(preamp.connectedTo).toEqual([filters[0]]);
    for (let i = 0; i < filters.length - 1; i += 1) {
      expect(filters[i].connectedTo).toEqual([filters[i + 1]]);
    }
    expect(filters[filters.length - 1].connectedTo).toEqual([context.destination]);
  });

  it('builds the graph once, however often it is attached', () => {
    attach(audioElement);
    attach(audioElement);

    expect(context.createMediaElementSource).toHaveBeenCalledTimes(1);
    expect(filtersOf(context)).toHaveLength(EQ_FREQUENCIES.length);
  });

  it('leaves the sound untouched until the equalizer is switched on', () => {
    attach(audioElement);
    setGains([6, 6, 6, 6, 6, 6, 6, 6, 6, 6]);
    setPreamp(-3);

    expect(filtersOf(context).every((f) => f.gain.value === 0)).toBe(true);
    expect(preampOf(context).gain.value).toBe(1);
  });

  it('applies stored gains once enabled and flattens them again once disabled', () => {
    attach(audioElement);
    setGains([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    setEnabled(true);

    expect(filtersOf(context).map((f) => f.gain.value)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);

    setEnabled(false);
    expect(filtersOf(context).map((f) => f.gain.value)).toEqual(Array.from({ length: 10 }, () => 0));

    setEnabled(true);
    expect(filtersOf(context).map((f) => f.gain.value)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  });

  it('moves one band without disturbing its neighbours', () => {
    attach(audioElement);
    setEnabled(true);
    setBand(3, -4.5);

    const gains = filtersOf(context).map((f) => f.gain.value);
    expect(gains[3]).toBe(-4.5);
    expect(gains.filter((g) => g !== 0)).toEqual([-4.5]);
  });

  it('converts the preamp from decibels to a linear gain', () => {
    attach(audioElement);
    setEnabled(true);

    setPreamp(0);
    expect(preampOf(context).gain.value).toBeCloseTo(1, 5);

    setPreamp(-6);
    expect(preampOf(context).gain.value).toBeCloseTo(0.5012, 3);

    setPreamp(6);
    expect(preampOf(context).gain.value).toBeCloseTo(1.9953, 3);
  });

  it('resumes a context the browser suspended, and leaves a running one alone', () => {
    attach(audioElement);

    context.state = 'suspended';
    resume();
    expect(context.resume).toHaveBeenCalledTimes(1);

    resume();
    expect(context.resume).toHaveBeenCalledTimes(1);
  });

  it('gives up quietly when the graph cannot be built', () => {
    __resetForTests();
    const broken = makeFakeContext({
      createMediaElementSource: vi.fn(() => { throw new Error('already connected'); }),
    });
    __setContextFactoryForTests(() => broken);
    vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(attach(audioElement)).toBe(false);
    expect(attach(audioElement)).toBe(false);
    expect(() => {
      setEnabled(true);
      setBand(0, 6);
      setGains(Array.from({ length: 10 }, () => 6));
      setPreamp(-3);
      resume();
    }).not.toThrow();
  });

  it('does nothing when there is no audio element to attach to', () => {
    expect(attach(null)).toBe(false);
    expect(context.createMediaElementSource).not.toHaveBeenCalled();
  });
});
