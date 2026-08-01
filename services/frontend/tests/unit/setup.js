import { vi } from 'vitest';
import '@testing-library/jest-dom/vitest';

// Mock localStorage
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => { store[key] = value.toString(); },
    clear: () => { store = {}; },
    removeItem: (key) => { delete store[key]; },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

// Mock fetch
global.fetch = vi.fn();

// jsdom reports `navigator.language` as en-US, so components would render in
// English here while the app they are part of is used in Dutch. Pinning the
// locale keeps assertions on interface text in the language the screens are
// actually read in, and keeps them from silently depending on the default.
const { setLocaleFromAccount } = await import('../../src/lib/i18n/index.js');
setLocaleFromAccount('nl');
