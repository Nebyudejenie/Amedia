import { describe, it, expect } from 'vitest';
import {
  contentUploadSchema,
  changePasswordSchema,
  profileSchema,
  verificationCodeSchema,
} from '@/lib/validators';

const validContent = {
  title: 'My feed',
  description: '',
  source_type: 'rss' as const,
  source_url: 'https://example.com/feed.xml',
  content_type: 'article' as const,
  tags: ['tech'],
  publish_now: true,
  schedule_date: '',
  schedule_time: '',
};

describe('contentUploadSchema', () => {
  it('accepts a valid RSS source', () => {
    expect(contentUploadSchema.safeParse(validContent).success).toBe(true);
  });

  it('requires URL for non-manual sources', () => {
    const result = contentUploadSchema.safeParse({ ...validContent, source_url: '' });
    expect(result.success).toBe(false);
  });

  it('allows missing URL for manual sources', () => {
    const result = contentUploadSchema.safeParse({
      ...validContent,
      source_type: 'manual',
      source_url: '',
    });
    expect(result.success).toBe(true);
  });

  it('requires future schedule when not publishing now', () => {
    const past = contentUploadSchema.safeParse({
      ...validContent,
      publish_now: false,
      schedule_date: '2020-01-01',
      schedule_time: '10:00',
    });
    expect(past.success).toBe(false);

    const future = contentUploadSchema.safeParse({
      ...validContent,
      publish_now: false,
      schedule_date: '2030-01-01',
      schedule_time: '10:00',
    });
    expect(future.success).toBe(true);
  });

  it('caps title at 200 chars and tags at 10', () => {
    expect(
      contentUploadSchema.safeParse({ ...validContent, title: 'x'.repeat(201) }).success
    ).toBe(false);
    expect(
      contentUploadSchema.safeParse({ ...validContent, tags: Array(11).fill('t') }).success
    ).toBe(false);
  });
});

describe('changePasswordSchema', () => {
  const valid = {
    current_password: 'OldPassword123!',
    new_password: 'NewPassword456!',
    confirm_password: 'NewPassword456!',
  };

  it('accepts a valid change', () => {
    expect(changePasswordSchema.safeParse(valid).success).toBe(true);
  });

  it('rejects when new password equals current', () => {
    const result = changePasswordSchema.safeParse({
      ...valid,
      new_password: valid.current_password,
      confirm_password: valid.current_password,
    });
    expect(result.success).toBe(false);
  });

  it('rejects mismatched confirmation', () => {
    expect(
      changePasswordSchema.safeParse({ ...valid, confirm_password: 'Different789!' }).success
    ).toBe(false);
  });
});

describe('profileSchema', () => {
  it('accepts a name and optional bio', () => {
    expect(profileSchema.safeParse({ full_name: 'Ada', bio: '' }).success).toBe(true);
  });

  it('caps name at 50 and bio at 500', () => {
    expect(profileSchema.safeParse({ full_name: 'x'.repeat(51) }).success).toBe(false);
    expect(profileSchema.safeParse({ full_name: 'Ada', bio: 'x'.repeat(501) }).success).toBe(false);
  });
});

describe('verificationCodeSchema', () => {
  it('accepts exactly six digits', () => {
    expect(verificationCodeSchema.safeParse({ code: '123456' }).success).toBe(true);
    expect(verificationCodeSchema.safeParse({ code: '12345' }).success).toBe(false);
    expect(verificationCodeSchema.safeParse({ code: '12345a' }).success).toBe(false);
  });
});
