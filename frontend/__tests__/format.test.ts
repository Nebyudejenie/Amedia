import { describe, it, expect } from 'vitest';
import { relativeTime, compactNumber, truncate, shortDate } from '@/lib/format';

describe('relativeTime', () => {
  it('formats hours ago', () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(relativeTime(twoHoursAgo)).toBe('2 hours ago');
  });

  it('formats just now', () => {
    expect(relativeTime(new Date().toISOString())).toBe('just now');
  });

  it('handles invalid dates', () => {
    expect(relativeTime('garbage')).toBe('—');
  });
});

describe('compactNumber', () => {
  it('compacts thousands and millions', () => {
    expect(compactNumber(999)).toBe('999');
    expect(compactNumber(12345)).toBe('12.3K');
    expect(compactNumber(1234567)).toBe('1.2M');
  });
});

describe('truncate', () => {
  it('truncates long strings with ellipsis at the max length', () => {
    const long = 'x'.repeat(80);
    const result = truncate(long, 50);
    expect(result).toHaveLength(50);
    expect(result.endsWith('…')).toBe(true);
  });

  it('leaves short strings untouched', () => {
    expect(truncate('short', 50)).toBe('short');
  });
});

describe('shortDate', () => {
  it('formats ISO dates for chart axes', () => {
    expect(shortDate('2026-06-11')).toMatch(/Jun 11/);
  });

  it('passes through invalid input', () => {
    expect(shortDate('n/a')).toBe('n/a');
  });
});
