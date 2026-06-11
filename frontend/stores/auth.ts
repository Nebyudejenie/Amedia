/** Auth store: holds the user object (tokens live in httpOnly cookies). */
import { create } from 'zustand';
import { authApi, type User } from '@/lib/api';

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isInitialized: boolean;
  setUser: (user: User | null) => void;
  fetchUser: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isLoading: false,
  isInitialized: false,

  setUser: (user) => set({ user, isInitialized: true }),

  fetchUser: async () => {
    set({ isLoading: true });
    try {
      const user = await authApi.me();
      set({ user, isInitialized: true });
    } catch {
      set({ user: null, isInitialized: true });
    } finally {
      set({ isLoading: false });
    }
  },

  logout: async () => {
    try {
      await authApi.logout();
    } finally {
      set({ user: null });
      window.location.href = '/auth/login';
    }
  },
}));
