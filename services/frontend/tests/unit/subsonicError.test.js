import { describe, it, expect } from 'vitest';
import { subsonicError } from '../../src/lib/utils.js';

function response(body, { ok = true, status = 200, statusText = 'OK' } = {}) {
  return { ok, status, statusText, json: async () => body };
}

describe('subsonicError', () => {
  it('returns null for a successful call', async () => {
    const result = await subsonicError(response({ 'subsonic-response': { status: 'ok' } }));

    expect(result).toBeNull();
  });

  // The whole reason this helper exists: Subsonic reports its own failures
  // with a 200, so response.ok says nothing about whether the call worked.
  it('reports a failure that arrived with HTTP 200', async () => {
    const result = await subsonicError(
      response({
        'subsonic-response': {
          status: 'failed',
          error: { code: 50, message: 'User is not authorized' },
        },
      }),
    );

    expect(result).toEqual({ code: 50, message: 'User is not authorized' });
  });

  it('reports a non-ok HTTP status', async () => {
    const result = await subsonicError(
      response(null, { ok: false, status: 503, statusText: 'Service Unavailable' }),
    );

    expect(result).toEqual({ code: null, message: 'Service Unavailable' });
  });

  it('falls back to the status number when there is no status text', async () => {
    const result = await subsonicError(response(null, { ok: false, status: 500, statusText: '' }));

    expect(result).toEqual({ code: null, message: 'HTTP 500' });
  });

  it('treats a body that is not JSON as a success', async () => {
    const broken = {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => {
        throw new SyntaxError('Unexpected token');
      },
    };

    await expect(subsonicError(broken)).resolves.toBeNull();
  });

  it('reports a failure that carries no error object', async () => {
    const result = await subsonicError(response({ 'subsonic-response': { status: 'failed' } }));

    expect(result).toEqual({ code: null, message: 'failed' });
  });
});
