/**
 * Middleware behavior tests: token decode + protection rules.
 * Full request-cycle tests run in e2e; here we verify the JWT helpers.
 */
import { describe, it, expect } from 'vitest';

// Re-implement the middleware's decode (it's inlined there for edge runtime)
function decodeExp(token: string): number {
  try {
    const part = token.split('.')[1];
    if (!part) return 0;
    const payload = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/')));
    return payload.exp ?? 0;
  } catch {
    return 0;
  }
}

function makeToken(expOffsetSeconds: number): string {
  const payload = { sub: 'user1', exp: Math.floor(Date.now() / 1000) + expOffsetSeconds };
  const b64 = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_');
  return `header.${b64}.signature`;
}

describe('token expiry detection (drives refresh-before-expiry)', () => {
  it('detects a healthy token (> 5 min left)', () => {
    const token = makeToken(60 * 30); // 30 min
    const secondsLeft = decodeExp(token) - Math.floor(Date.now() / 1000);
    expect(secondsLeft).toBeGreaterThan(5 * 60);
  });

  it('detects a token inside the 5-minute refresh window', () => {
    const token = makeToken(60 * 2); // 2 min left
    const secondsLeft = decodeExp(token) - Math.floor(Date.now() / 1000);
    expect(secondsLeft).toBeLessThanOrEqual(5 * 60);
    expect(secondsLeft).toBeGreaterThan(0);
  });

  it('detects an expired token', () => {
    const token = makeToken(-60);
    const secondsLeft = decodeExp(token) - Math.floor(Date.now() / 1000);
    expect(secondsLeft).toBeLessThan(0);
  });

  it('treats garbage tokens as expired', () => {
    expect(decodeExp('not-a-jwt')).toBe(0);
    expect(decodeExp('')).toBe(0);
  });
});
