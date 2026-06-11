import { describe, it, expect } from 'vitest';
import { passwordSchema, passwordStrength, registerSchema } from '@/lib/validators';

describe('passwordSchema', () => {
  it('accepts a strong password', () => {
    expect(passwordSchema.safeParse('SuperSecure123!').success).toBe(true);
  });

  it.each([
    ['Short1!aA', 'too short'],
    ['alllowercase123!!!!', 'no uppercase'],
    ['NoNumbersHere!!!ABC', 'no number'],
    ['NoSymbolsHere123ABC', 'no symbol'],
  ])('rejects %s (%s)', (password) => {
    expect(passwordSchema.safeParse(password).success).toBe(false);
  });
});

describe('passwordStrength', () => {
  it('scores empty as 0', () => {
    expect(passwordStrength('').score).toBe(0);
  });

  it('scores a strong password as 4 / green', () => {
    const result = passwordStrength('SuperSecure123!');
    expect(result.score).toBe(4);
    expect(result.color).toBe('bg-green-500');
  });

  it('scores weak passwords red/orange', () => {
    expect(passwordStrength('abc').color).toMatch(/red|orange/);
  });
});

describe('registerSchema', () => {
  const valid = {
    full_name: 'Ada Lovelace',
    email: 'ada@example.com',
    password: 'SuperSecure123!',
    confirmPassword: 'SuperSecure123!',
    acceptTerms: true as const,
  };

  it('accepts valid registration', () => {
    expect(registerSchema.safeParse(valid).success).toBe(true);
  });

  it('rejects mismatched passwords', () => {
    const result = registerSchema.safeParse({ ...valid, confirmPassword: 'Different123!' });
    expect(result.success).toBe(false);
  });

  it('requires terms acceptance', () => {
    const result = registerSchema.safeParse({ ...valid, acceptTerms: false });
    expect(result.success).toBe(false);
  });
});
