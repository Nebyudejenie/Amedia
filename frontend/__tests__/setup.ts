import '@testing-library/jest-dom';
import { vi } from 'vitest';

// next/navigation mocks shared by all tests
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/auth/login',
}));
